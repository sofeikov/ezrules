import hashlib
import os
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ezrules.backend import api_key_cache, observation_queue
from ezrules.backend.runtime_settings import bump_api_key_cache_version
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import drain_field_observation_queue
from ezrules.models.backend_core import ApiKey, FieldObservation, Organisation
from ezrules.models.database import engine
from ezrules.settings import app_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("EZRULES_LIVE_REDIS_CELERY_SMOKE") != "true",
    reason="live Redis/Celery smoke tests run only in the dedicated CI lane",
)


SMOKE_ORG_ID = 1
SMOKE_API_KEY_LABEL = "live-redis-celery-smoke"
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_smoke_org(session: Session) -> None:
    if session.get(Organisation, SMOKE_ORG_ID) is None:
        session.add(Organisation(o_id=SMOKE_ORG_ID, name="Live Redis Celery Smoke"))


@pytest.fixture(autouse=True)
def reset_live_smoke_state() -> Iterator[Redis]:
    redis_client = Redis.from_url(app_settings.CELERY_BROKER_URL, decode_responses=True)
    redis_client.delete(
        app_settings.OBSERVATION_QUEUE_KEY,
        app_settings.OBSERVATION_QUEUE_LOCK_KEY,
        f"ezrules:api_key_auth_version:{SMOKE_ORG_ID}",
    )
    observation_queue.get_observation_queue_client.cache_clear()
    api_key_cache.reset_api_key_auth_cache()
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False

    with _session_scope() as session:
        _ensure_smoke_org(session)
        session.query(FieldObservation).filter(FieldObservation.o_id == SMOKE_ORG_ID).delete()
        session.query(ApiKey).filter(ApiKey.label == SMOKE_API_KEY_LABEL).delete()

    yield redis_client

    redis_client.delete(
        app_settings.OBSERVATION_QUEUE_KEY,
        app_settings.OBSERVATION_QUEUE_LOCK_KEY,
        f"ezrules:api_key_auth_version:{SMOKE_ORG_ID}",
    )
    observation_queue.get_observation_queue_client.cache_clear()
    api_key_cache.reset_api_key_auth_cache()


def test_real_celery_worker_drains_observation_queue_through_redis(reset_live_smoke_state: Redis):
    redis_client = reset_live_smoke_state

    queued = observation_queue.enqueue_observations(
        {"amount": 500, "country": "US", "risk": {"score": 0.82}},
        SMOKE_ORG_ID,
    )

    assert queued is True
    assert redis_client.llen(app_settings.OBSERVATION_QUEUE_KEY) == 1

    held_lock = redis_client.lock(
        app_settings.OBSERVATION_QUEUE_LOCK_KEY,
        timeout=30,
        blocking=False,
    )
    assert held_lock.acquire(blocking=False) is True

    try:
        skipped_result = drain_field_observation_queue.apply_async().get(timeout=20)
    finally:
        held_lock.release()

    assert skipped_result == {"drained_batches": 0, "drained_messages": 0}
    assert redis_client.llen(app_settings.OBSERVATION_QUEUE_KEY) == 1

    drained_result = drain_field_observation_queue.apply_async().get(timeout=20)

    assert drained_result == {"drained_batches": 1, "drained_messages": 1}
    assert redis_client.llen(app_settings.OBSERVATION_QUEUE_KEY) == 0

    with _session_scope() as session:
        observed_rows = [
            (row.field_name, row.observed_json_type)
            for row in (
                session.query(FieldObservation)
                .filter(FieldObservation.o_id == SMOKE_ORG_ID)
                .order_by(FieldObservation.field_name, FieldObservation.observed_json_type)
                .all()
            )
        ]

    assert observed_rows == [
        ("amount", "int"),
        ("country", "str"),
        ("risk", "dict"),
        ("risk.score", "float"),
    ]


def test_real_redis_cache_version_invalidates_stale_api_key_metadata(reset_live_smoke_state: Redis):
    redis_client = reset_live_smoke_state
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    worker_one_cache = api_key_cache.ApiKeyAuthCache()
    worker_two_cache = api_key_cache.ApiKeyAuthCache()

    with _session_scope() as session:
        _ensure_smoke_org(session)
        session.add(
            ApiKey(
                gid=str(uuid.uuid4()),
                key_hash=key_hash,
                label=SMOKE_API_KEY_LABEL,
                o_id=SMOKE_ORG_ID,
            )
        )

    with _session_scope() as session:
        assert worker_one_cache.load(session, raw_key) == api_key_cache.ApiKeyAuthMetadata(org_id=SMOKE_ORG_ID)
        assert worker_two_cache.load(session, raw_key) == api_key_cache.ApiKeyAuthMetadata(org_id=SMOKE_ORG_ID)

    assert redis_client.get(f"ezrules:api_key_auth_version:{SMOKE_ORG_ID}") == "0"

    with _session_scope() as session:
        api_key = session.query(ApiKey).filter(ApiKey.key_hash == key_hash).one()
        api_key.revoked_at = datetime.now(UTC)
        next_version = bump_api_key_cache_version(session, SMOKE_ORG_ID)

    assert worker_one_cache.publish(SMOKE_ORG_ID, next_version) is True
    assert redis_client.get(f"ezrules:api_key_auth_version:{SMOKE_ORG_ID}") == str(next_version)

    with _session_scope() as session:
        assert worker_two_cache.load(session, raw_key) is None
