import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from ezrules.core.notification_channel_config import redact_notification_channel_error
from ezrules.models.backend_core import (
    InAppNotification,
    NotificationAttempt,
    NotificationChannel,
    NotificationPolicy,
)

logger = logging.getLogger(__name__)

SAFE_REDACTION_FALLBACK_ERROR = "Notification delivery failed; error details could not be safely redacted"


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    title: str
    body: str
    severity: str
    source_type: str
    source_id: int
    action_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: str
    error: str | None = None


class NotificationChannelAdapter(Protocol):
    channel_type: str

    def send(self, db: Any, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult: ...


class InAppChannelAdapter:
    channel_type = "in_app"

    def send(self, db: Any, channel: NotificationChannel, message: NotificationMessage) -> DeliveryResult:
        notification = InAppNotification(
            o_id=channel.o_id,
            severity=message.severity,
            title=message.title,
            body=message.body,
            action_url=message.action_url,
            source_type=message.source_type,
            source_id=message.source_id,
        )
        db.add(notification)
        return DeliveryResult(status="success")


CHANNEL_ADAPTERS: dict[str, NotificationChannelAdapter] = {
    InAppChannelAdapter.channel_type: InAppChannelAdapter(),
}


def ensure_in_app_channel(db: Any, o_id: int) -> NotificationChannel:
    channel = (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.o_id == o_id,
            NotificationChannel.channel_type == "in_app",
            NotificationChannel.name == "In-app",
        )
        .first()
    )
    if channel is not None:
        return channel

    channel = NotificationChannel(
        o_id=o_id,
        name="In-app",
        channel_type="in_app",
        enabled=True,
        config={},
    )
    db.add(channel)
    db.flush()
    return channel


def ensure_default_policy(db: Any, *, o_id: int, alert_rule_id: int) -> None:
    channel = ensure_in_app_channel(db, o_id)
    existing = (
        db.query(NotificationPolicy)
        .filter(
            NotificationPolicy.o_id == o_id,
            NotificationPolicy.alert_rule_id == alert_rule_id,
            NotificationPolicy.notification_channel_id == channel.nc_id,
        )
        .first()
    )
    if existing is not None:
        return

    db.add(
        NotificationPolicy(
            o_id=o_id,
            alert_rule_id=alert_rule_id,
            notification_channel_id=channel.nc_id,
            enabled=True,
        )
    )


def _redact_delivery_error(channel: NotificationChannel, error: str | None) -> str | None:
    if error is None:
        return None

    try:
        config = channel.config
    except Exception:
        logger.warning("Notification channel %s config could not be read while redacting error", channel.nc_id)
        config = None

    try:
        return redact_notification_channel_error(str(channel.channel_type), config, error)
    except Exception:
        logger.exception("Notification channel %s error redaction failed", channel.nc_id)
        return SAFE_REDACTION_FALLBACK_ERROR


def dispatch_notification(
    db: Any, *, o_id: int, alert_rule_id: int, incident_id: int, message: NotificationMessage
) -> None:
    policies = (
        db.query(NotificationPolicy, NotificationChannel)
        .join(NotificationChannel, NotificationChannel.nc_id == NotificationPolicy.notification_channel_id)
        .filter(
            NotificationPolicy.o_id == o_id,
            NotificationPolicy.alert_rule_id == alert_rule_id,
            NotificationPolicy.enabled.is_(True),
            NotificationChannel.enabled.is_(True),
        )
        .all()
    )

    if not policies:
        ensure_default_policy(db, o_id=o_id, alert_rule_id=alert_rule_id)
        policies = (
            db.query(NotificationPolicy, NotificationChannel)
            .join(NotificationChannel, NotificationChannel.nc_id == NotificationPolicy.notification_channel_id)
            .filter(
                NotificationPolicy.o_id == o_id,
                NotificationPolicy.alert_rule_id == alert_rule_id,
                NotificationPolicy.enabled.is_(True),
                NotificationChannel.enabled.is_(True),
            )
            .all()
        )

    for _policy, channel in policies:
        adapter = CHANNEL_ADAPTERS.get(str(channel.channel_type))
        if adapter is None:
            db.add(
                NotificationAttempt(
                    o_id=o_id,
                    alert_incident_id=incident_id,
                    notification_channel_id=channel.nc_id,
                    status="unsupported",
                    error=f"Unsupported notification channel type: {channel.channel_type}",
                )
            )
            continue

        try:
            result = adapter.send(db, channel, message)
        except Exception as exc:
            logger.exception("Notification channel %s failed for incident %s", channel.nc_id, incident_id)
            result = DeliveryResult(
                status="failure",
                error=_redact_delivery_error(channel, str(exc)),
            )
        else:
            result = DeliveryResult(status=result.status, error=_redact_delivery_error(channel, result.error))

        db.add(
            NotificationAttempt(
                o_id=o_id,
                alert_incident_id=incident_id,
                notification_channel_id=channel.nc_id,
                status=result.status,
                error=result.error,
            )
        )
