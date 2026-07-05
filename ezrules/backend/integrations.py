from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import requests

from ezrules.models.backend_core import IntegrationEvent, IntegrationOutbox, IntegrationSubscription

logger = logging.getLogger(__name__)

INTEGRATION_EVENT_VERSION = 1
OUTBOX_PENDING = "pending"
OUTBOX_DELIVERED = "delivered"
OUTBOX_FAILED = "failed"
OUTBOX_DEAD_LETTERED = "dead_lettered"
OUTBOX_SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class IntegrationPublishResult:
    event: IntegrationEvent
    delivery_count: int


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _new_event_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _subscription_matches(subscription: IntegrationSubscription, event_type: str) -> bool:
    configured = subscription.event_types if isinstance(subscription.event_types, list) else []
    if not configured:
        return True
    return event_type in {str(item) for item in configured}


def _subscriptions_for_event(db: Any, *, o_id: int, event_type: str) -> list[IntegrationSubscription]:
    subscriptions = (
        db.query(IntegrationSubscription)
        .filter(IntegrationSubscription.o_id == o_id, IntegrationSubscription.enabled.is_(True))
        .all()
    )
    return [subscription for subscription in subscriptions if _subscription_matches(subscription, event_type)]


def _enqueue_outbox_deliveries(db: Any, *, event: IntegrationEvent) -> int:
    delivery_count = 0
    for subscription in _subscriptions_for_event(db, o_id=int(event.o_id), event_type=str(event.event_type)):
        existing = (
            db.query(IntegrationOutbox.delivery_id)
            .filter(
                IntegrationOutbox.integration_event_id == int(event.integration_event_id),
                IntegrationOutbox.subscription_id == int(subscription.subscription_id),
            )
            .first()
        )
        if existing is not None:
            continue
        db.add(
            IntegrationOutbox(
                o_id=int(event.o_id),
                integration_event_id=int(event.integration_event_id),
                subscription_id=int(subscription.subscription_id),
                destination_type=str(subscription.destination_type),
                status=OUTBOX_PENDING,
                attempt_count=0,
                next_attempt_at=_utcnow(),
            )
        )
        delivery_count += 1
    return delivery_count


def publish_integration_event(
    db: Any,
    *,
    o_id: int,
    source_type: str,
    source_id: int,
    event_type: str,
    payload: dict[str, Any],
    external_event_id: str | None = None,
    occurred_at: datetime.datetime | None = None,
) -> IntegrationPublishResult:
    if external_event_id is not None:
        existing = db.query(IntegrationEvent).filter(IntegrationEvent.external_event_id == external_event_id).first()
        if existing is not None:
            return IntegrationPublishResult(
                event=existing, delivery_count=_enqueue_outbox_deliveries(db, event=existing)
            )

    event = IntegrationEvent(
        external_event_id=external_event_id or _new_event_id(),
        o_id=o_id,
        source_type=source_type,
        source_id=source_id,
        event_type=event_type,
        event_version=INTEGRATION_EVENT_VERSION,
        occurred_at=occurred_at or _utcnow(),
        payload=payload,
        created_at=_utcnow(),
    )
    db.add(event)
    db.flush()

    return IntegrationPublishResult(event=event, delivery_count=_enqueue_outbox_deliveries(db, event=event))


def list_integration_events(
    db: Any,
    *,
    o_id: int,
    after_id: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[IntegrationEvent]:
    query = db.query(IntegrationEvent).filter(IntegrationEvent.o_id == o_id)
    if after_id is not None:
        query = query.filter(IntegrationEvent.integration_event_id > after_id)
    if event_type:
        query = query.filter(IntegrationEvent.event_type == event_type)
    return query.order_by(IntegrationEvent.integration_event_id.asc()).limit(limit).all()


def _signature(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _deliver_webhook(subscription: IntegrationSubscription, event: IntegrationEvent) -> None:
    config = subscription.config if isinstance(subscription.config, dict) else {}
    url = str(config.get("url") or "").strip()
    if not url:
        raise ValueError("Webhook subscription is missing config.url")

    payload = {
        "event_id": event.external_event_id,
        "event_type": event.event_type,
        "event_version": event.event_version,
        "occurred_at": event.occurred_at.isoformat(),
        "organisation_id": event.o_id,
        "payload": event.payload,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    headers = {"Content-Type": "application/json", "X-Ezrules-Event-Id": str(event.external_event_id)}
    configured_headers = config.get("headers")
    if isinstance(configured_headers, dict):
        headers.update({str(key): str(value) for key, value in configured_headers.items()})
    secret = str(config.get("secret") or subscription.secret_ref or "")
    if secret:
        headers["X-Ezrules-Signature"] = _signature(secret, body)

    response = requests.post(url, data=body, headers=headers, timeout=10)
    if response.status_code >= 400:
        raise ValueError(f"Webhook returned HTTP {response.status_code}")


def dispatch_pending_outbox(db: Any, *, limit: int = 100) -> dict[str, int]:
    now = _utcnow()
    deliveries = (
        db.query(IntegrationOutbox, IntegrationEvent, IntegrationSubscription)
        .join(IntegrationEvent, IntegrationEvent.integration_event_id == IntegrationOutbox.integration_event_id)
        .join(IntegrationSubscription, IntegrationSubscription.subscription_id == IntegrationOutbox.subscription_id)
        .filter(
            IntegrationOutbox.status.in_([OUTBOX_PENDING, OUTBOX_FAILED]),
            IntegrationOutbox.next_attempt_at <= now,
        )
        .order_by(IntegrationOutbox.next_attempt_at.asc(), IntegrationOutbox.delivery_id.asc())
        .with_for_update(skip_locked=True, of=IntegrationOutbox)
        .limit(limit)
        .all()
    )

    delivered = 0
    failed = 0
    for delivery, event, subscription in deliveries:
        if not bool(subscription.enabled):
            delivery.status = OUTBOX_SKIPPED
            delivery.last_error = "Subscription disabled before delivery"
            delivery.updated_at = _utcnow()
            continue
        delivery.attempt_count = int(delivery.attempt_count or 0) + 1
        delivery.last_attempted_at = now
        try:
            if subscription.destination_type == "webhook":
                _deliver_webhook(subscription, event)
            else:
                raise ValueError(f"Unsupported integration destination: {subscription.destination_type}")
        except Exception as exc:
            logger.exception("Integration delivery failed for delivery_id=%s", delivery.delivery_id)
            delivery.last_error = str(exc)
            delivery.status = OUTBOX_DEAD_LETTERED if delivery.attempt_count >= 10 else OUTBOX_FAILED
            delay_seconds = min(3600, 30 * (2 ** min(delivery.attempt_count - 1, 6)))
            delivery.next_attempt_at = now + datetime.timedelta(seconds=delay_seconds)
            failed += 1
        else:
            delivery.status = OUTBOX_DELIVERED
            delivery.last_error = None
            delivered += 1
        delivery.updated_at = _utcnow()
    db.commit()
    return {"delivered": delivered, "failed": failed}
