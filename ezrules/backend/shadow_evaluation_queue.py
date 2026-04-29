import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from redis import Redis

from ezrules.backend.runtime_settings import get_main_rule_execution_mode
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.rule_engine import RULE_EXECUTION_MODE_ALL_MATCHES, RuleEngineFactory
from ezrules.core.rule_updater import (
    DEPLOYMENT_MODE_SHADOW,
    DEPLOYMENT_VARIANT_CONTROL,
    SHADOW_CONFIG_LABEL,
    get_deployment_config,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import RuleDeploymentResultsLog, ShadowResultsLog
from ezrules.models.database import db_session
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)


def _shadow_queue_url() -> str:
    return app_settings.SHADOW_EVALUATION_QUEUE_REDIS_URL or app_settings.CELERY_BROKER_URL


@lru_cache(maxsize=1)
def get_shadow_evaluation_queue_client() -> Redis:
    return Redis.from_url(_shadow_queue_url(), decode_responses=True)


def _serialize_shadow_payload(
    *,
    o_id: int,
    event_id: str,
    event_data: dict[str, Any],
    production_all_rule_results: dict[Any, Any],
    evaluation_decision_id: int | None,
    event_version_id: int | None,
    shadow_config: list[dict[str, Any]],
    shadow_config_version: int,
    main_rule_execution_mode: str,
) -> str:
    return json.dumps(
        {
            "o_id": o_id,
            "event_id": event_id,
            "event_data": event_data,
            "evaluation_decision_id": evaluation_decision_id,
            "event_version_id": event_version_id,
            "production_all_rule_results": {str(r_id): result for r_id, result in production_all_rule_results.items()},
            "shadow_config": shadow_config,
            "shadow_config_version": shadow_config_version,
            "main_rule_execution_mode": main_rule_execution_mode,
            "enqueued_at": datetime.now(UTC).isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def enqueue_shadow_evaluation(
    *,
    db,
    o_id: int,
    event_id: str,
    event_data: dict[str, Any],
    production_all_rule_results: dict[Any, Any],
    evaluation_decision_id: int | None = None,
    event_version_id: int | None = None,
) -> bool:
    config_obj = get_deployment_config(db, o_id=o_id, label=SHADOW_CONFIG_LABEL)
    if config_obj is None or not config_obj.config:
        return False
    shadow_config = list(config_obj.config) if isinstance(config_obj.config, list) else []
    if not shadow_config:
        return False

    payload = _serialize_shadow_payload(
        o_id=o_id,
        event_id=event_id,
        event_data=event_data,
        production_all_rule_results=production_all_rule_results,
        evaluation_decision_id=evaluation_decision_id,
        event_version_id=event_version_id,
        shadow_config=shadow_config,
        shadow_config_version=int(config_obj.version),
        main_rule_execution_mode=get_main_rule_execution_mode(db, o_id),
    )
    try:
        get_shadow_evaluation_queue_client().lpush(app_settings.SHADOW_EVALUATION_QUEUE_KEY, payload)
    except Exception:
        logger.exception("Failed to enqueue shadow evaluation for event_id=%s org_id=%s", event_id, o_id)
        return False
    return True


def _normalize_batch(raw_batch: str | list[str] | None) -> list[str]:
    if raw_batch is None:
        return []
    if isinstance(raw_batch, list):
        return raw_batch
    return [raw_batch]


def _requeue_payloads(payloads: list[str]) -> None:
    if not payloads:
        return
    get_shadow_evaluation_queue_client().rpush(app_settings.SHADOW_EVALUATION_QUEUE_KEY, *reversed(payloads))


def _parse_enqueued_at(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    try:
        return datetime.fromisoformat(str(raw_value))
    except ValueError:
        return None


def _persist_shadow_results(payload: dict[str, Any]) -> int:
    o_id = int(payload["o_id"])
    evaluation_decision_id = int(payload["evaluation_decision_id"])
    event_id = str(payload.get("event_id") or "")
    event_data = dict(payload.get("event_data") or {})
    production_all_rule_results = {
        int(r_id): result for r_id, result in dict(payload.get("production_all_rule_results") or {}).items()
    }
    shadow_config = list(payload.get("shadow_config") or [])
    main_rule_execution_mode = str(payload.get("main_rule_execution_mode") or RULE_EXECUTION_MODE_ALL_MATCHES)

    if not shadow_config:
        return 0

    list_provider = PersistentUserListManager(db_session=db_session, o_id=o_id)
    set_organization_id(o_id)
    set_user_list_manager(list_provider)

    shadow_engine = RuleEngineFactory.from_json(
        shadow_config,
        list_values_provider=list_provider,
        execution_mode=main_rule_execution_mode,
    )
    shadow_result = shadow_engine(event_data)

    persisted_logs = 0
    try:
        for r_id, rule_result in shadow_result.get("all_rule_results", {}).items():
            db_session.add(
                ShadowResultsLog(
                    ed_id=evaluation_decision_id,
                    r_id=int(r_id),
                    rule_result=str(rule_result),
                )
            )
            db_session.add(
                RuleDeploymentResultsLog(
                    ed_id=evaluation_decision_id,
                    r_id=int(r_id),
                    o_id=o_id,
                    mode=DEPLOYMENT_MODE_SHADOW,
                    selected_variant=DEPLOYMENT_VARIANT_CONTROL,
                    traffic_percent=None,
                    bucket=None,
                    control_result=str(production_all_rule_results.get(int(r_id)))
                    if production_all_rule_results.get(int(r_id)) is not None
                    else None,
                    candidate_result=str(rule_result) if rule_result is not None else None,
                    returned_result=str(production_all_rule_results.get(int(r_id)))
                    if production_all_rule_results.get(int(r_id)) is not None
                    else None,
                )
            )
            persisted_logs += 1
        db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception("Failed to persist shadow results for event_id=%s org_id=%s", event_id, o_id)
        raise

    return persisted_logs


def _max_enqueue_lag_seconds(payloads: Iterable[str]) -> int:
    now = datetime.now(UTC)
    max_age_seconds = 0
    for payload in payloads:
        parsed = json.loads(payload)
        enqueued_at = _parse_enqueued_at(parsed.get("enqueued_at"))
        if enqueued_at is None:
            continue
        age_seconds = int(max((now - enqueued_at).total_seconds(), 0))
        if age_seconds > max_age_seconds:
            max_age_seconds = age_seconds
    return max_age_seconds


def drain_shadow_evaluation_queue(
    *,
    batch_size: int | None = None,
    max_batches: int | None = None,
) -> dict[str, int]:
    client = get_shadow_evaluation_queue_client()
    lock = client.lock(
        app_settings.SHADOW_EVALUATION_QUEUE_LOCK_KEY,
        timeout=app_settings.SHADOW_EVALUATION_QUEUE_LOCK_TIMEOUT_SECONDS,
        blocking=False,
    )
    if not lock.acquire(blocking=False):
        return {"drained_batches": 0, "drained_messages": 0, "max_enqueue_lag_seconds": 0}

    effective_batch_size = batch_size or app_settings.SHADOW_EVALUATION_QUEUE_DRAIN_BATCH_SIZE
    effective_max_batches = max_batches or app_settings.SHADOW_EVALUATION_QUEUE_MAX_BATCHES_PER_DRAIN
    drained_batches = 0
    drained_messages = 0
    max_enqueue_lag_seconds = 0

    try:
        for _ in range(effective_max_batches):
            payloads = _normalize_batch(client.rpop(app_settings.SHADOW_EVALUATION_QUEUE_KEY, effective_batch_size))
            if not payloads:
                break

            max_enqueue_lag_seconds = max(max_enqueue_lag_seconds, _max_enqueue_lag_seconds(payloads))
            try:
                for payload in payloads:
                    _persist_shadow_results(json.loads(payload))
            except Exception:
                _requeue_payloads(payloads)
                raise

            drained_batches += 1
            drained_messages += len(payloads)
            if len(payloads) < effective_batch_size:
                break
    finally:
        lock.release()

    return {
        "drained_batches": drained_batches,
        "drained_messages": drained_messages,
        "max_enqueue_lag_seconds": max_enqueue_lag_seconds,
    }
