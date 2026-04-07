import json
import logging
from collections.abc import Iterable
from functools import lru_cache

from redis import Redis

from ezrules.backend.utils import upsert_field_observations
from ezrules.models.database import db_session
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)


ObservationKey = tuple[int, str, str]


def _observation_queue_url() -> str:
    return app_settings.OBSERVATION_QUEUE_REDIS_URL or app_settings.CELERY_BROKER_URL


@lru_cache(maxsize=1)
def get_observation_queue_client() -> Redis:
    return Redis.from_url(_observation_queue_url(), decode_responses=True)


def _build_observation_entries(event_data: dict) -> list[dict[str, str]]:
    return [
        {
            "field_name": field_name,
            "observed_json_type": type(value).__name__,
        }
        for field_name, value in event_data.items()
    ]


def enqueue_observations(event_data: dict, o_id: int) -> bool:
    if not event_data:
        return False

    payload = json.dumps(
        {
            "o_id": o_id,
            "observations": _build_observation_entries(event_data),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        get_observation_queue_client().lpush(app_settings.OBSERVATION_QUEUE_KEY, payload)
    except Exception:
        logger.exception("Failed to enqueue field observations for org_id=%s", o_id)
        return False
    return True


def _normalize_batch(raw_batch: str | list[str] | None) -> list[str]:
    if raw_batch is None:
        return []
    if isinstance(raw_batch, list):
        return raw_batch
    return [raw_batch]


def _aggregate_payloads(
    payloads: Iterable[str],
) -> list[dict[str, str | int]]:
    observation_keys: set[ObservationKey] = set()

    for payload in payloads:
        message = json.loads(payload)
        o_id = int(message["o_id"])
        observations = message.get("observations", [])
        for observation in observations:
            observation_keys.add(
                (
                    o_id,
                    str(observation["field_name"]),
                    str(observation["observed_json_type"]),
                )
            )

    return [
        {
            "o_id": o_id,
            "field_name": field_name,
            "observed_json_type": observed_json_type,
        }
        for o_id, field_name, observed_json_type in observation_keys
    ]


def _requeue_payloads(payloads: list[str]) -> None:
    if not payloads:
        return
    get_observation_queue_client().rpush(app_settings.OBSERVATION_QUEUE_KEY, *reversed(payloads))


def drain_observation_queue(
    *,
    batch_size: int | None = None,
    max_batches: int | None = None,
) -> dict[str, int]:
    client = get_observation_queue_client()
    lock = client.lock(
        app_settings.OBSERVATION_QUEUE_LOCK_KEY,
        timeout=app_settings.OBSERVATION_QUEUE_LOCK_TIMEOUT_SECONDS,
        blocking=False,
    )
    if not lock.acquire(blocking=False):
        return {"drained_batches": 0, "drained_messages": 0}

    effective_batch_size = batch_size or app_settings.OBSERVATION_QUEUE_DRAIN_BATCH_SIZE
    effective_max_batches = max_batches or app_settings.OBSERVATION_QUEUE_MAX_BATCHES_PER_DRAIN
    drained_batches = 0
    drained_messages = 0

    try:
        for _ in range(effective_max_batches):
            payloads = _normalize_batch(client.rpop(app_settings.OBSERVATION_QUEUE_KEY, effective_batch_size))
            if not payloads:
                break

            try:
                observation_rows = _aggregate_payloads(payloads)
                if observation_rows:
                    upsert_field_observations(
                        db_session,
                        observation_rows,
                    )
            except Exception:
                db_session.rollback()
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
    }
