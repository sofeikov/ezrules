import hashlib
import secrets
import uuid

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend import api_key_cache
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, ApiKey, Organisation, Role, RoleActions, User


class FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str, nx: bool = False) -> bool:
        if nx and key in self._values:
            return False
        self._values[key] = str(value)
        return True


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture(autouse=True)
def reset_api_key_cache_state():
    api_key_cache.reset_api_key_auth_cache()
    yield
    api_key_cache.reset_api_key_auth_cache()
    evaluator_router._lre = None


@pytest.fixture(scope="function")
def org(session):
    return session.query(Organisation).one()


@pytest.fixture(scope="function")
def live_api_key(session, org):
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="cache-test-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


def _create_api_key_manager_token(session, org: Organisation) -> str:
    hashed_password = bcrypt.hashpw("cachepass".encode(), bcrypt.gensalt()).decode()

    role = session.query(Role).filter(Role.name == "api_key_cache_manager", Role.o_id == org.o_id).first()
    if role is None:
        role = Role(name="api_key_cache_manager", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "api-key-cache-manager@example.com", User.o_id == org.o_id).first()
    if user is None:
        user = User(
            email="api-key-cache-manager@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier=f"api-key-cache-manager-{uuid.uuid4().hex}",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    action = session.query(Action).filter(Action.name == PermissionAction.MANAGE_API_KEYS.value).first()
    assert action is not None
    existing = session.query(RoleActions).filter_by(role_id=role.id, action_id=action.id).first()
    if existing is None:
        session.add(RoleActions(role_id=role.id, action_id=action.id))
        session.commit()

    return create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(org.o_id))


def test_api_key_auth_cache_reuses_worker_memory_when_version_is_stable(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    cache = api_key_cache.ApiKeyAuthCache(client_getter=lambda: fake_redis)
    load_calls: list[str] = []

    def _fake_load(db, key_hash: str) -> api_key_cache.ApiKeyAuthMetadata | None:
        del db
        load_calls.append(key_hash)
        return api_key_cache.ApiKeyAuthMetadata(org_id=42)

    monkeypatch.setattr(api_key_cache, "_load_api_key_auth_metadata_from_db", _fake_load)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, org_id: "0")

    assert cache.load_hashed(object(), "key-hash") == api_key_cache.ApiKeyAuthMetadata(org_id=42)
    assert cache.load_hashed(object(), "key-hash") == api_key_cache.ApiKeyAuthMetadata(org_id=42)
    assert load_calls == ["key-hash"]


def test_api_key_auth_cache_invalidation_refreshes_other_worker(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    worker_one = api_key_cache.ApiKeyAuthCache(client_getter=lambda: fake_redis)
    worker_two = api_key_cache.ApiKeyAuthCache(client_getter=lambda: fake_redis)
    load_calls: list[str] = []
    org_id = {"value": 7}
    durable_version = {"value": "1"}

    def _fake_load(db, key_hash: str) -> api_key_cache.ApiKeyAuthMetadata | None:
        del db
        load_calls.append(key_hash)
        return api_key_cache.ApiKeyAuthMetadata(org_id=org_id["value"])

    monkeypatch.setattr(api_key_cache, "_load_api_key_auth_metadata_from_db", _fake_load)
    monkeypatch.setattr(worker_one, "_read_durable_version", lambda db, org_id: durable_version["value"])
    monkeypatch.setattr(worker_two, "_read_durable_version", lambda db, org_id: durable_version["value"])

    assert worker_one.load_hashed(object(), "shared-key") == api_key_cache.ApiKeyAuthMetadata(org_id=7)
    assert worker_two.load_hashed(object(), "shared-key") == api_key_cache.ApiKeyAuthMetadata(org_id=7)

    durable_version["value"] = "2"
    assert worker_one.publish(7, 2) is True

    assert worker_two.load_hashed(object(), "shared-key") == api_key_cache.ApiKeyAuthMetadata(org_id=7)
    assert load_calls == ["shared-key", "shared-key", "shared-key"]


def test_api_key_auth_cache_recovers_from_redis_key_loss(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    cache = api_key_cache.ApiKeyAuthCache(client_getter=lambda: fake_redis)
    load_calls: list[str] = []

    def _fake_load(db, key_hash: str) -> api_key_cache.ApiKeyAuthMetadata | None:
        del db
        load_calls.append(key_hash)
        return api_key_cache.ApiKeyAuthMetadata(org_id=3)

    monkeypatch.setattr(api_key_cache, "_load_api_key_auth_metadata_from_db", _fake_load)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, org_id: "2")

    assert cache.load_hashed(object(), "lost-redis-key") == api_key_cache.ApiKeyAuthMetadata(org_id=3)

    fake_redis._values.clear()

    assert cache.load_hashed(object(), "lost-redis-key") == api_key_cache.ApiKeyAuthMetadata(org_id=3)
    assert fake_redis.get("ezrules:api_key_auth_version:3") == "2"
    assert load_calls == ["lost-redis-key"]


def test_api_key_auth_cache_refreshes_from_durable_version_after_ttl_when_publish_was_missed(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = FakeRedis()
    fake_clock = FakeMonotonic()
    cache = api_key_cache.ApiKeyAuthCache(client_getter=lambda: fake_redis)
    load_calls: list[str] = []
    org_id = {"value": 9}
    durable_version = {"value": "1"}

    def _fake_load(db, key_hash: str) -> api_key_cache.ApiKeyAuthMetadata | None:
        del db
        load_calls.append(key_hash)
        return api_key_cache.ApiKeyAuthMetadata(org_id=org_id["value"])

    monkeypatch.setattr(api_key_cache, "_load_api_key_auth_metadata_from_db", _fake_load)
    monkeypatch.setattr(api_key_cache, "monotonic", fake_clock)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, org_id: durable_version["value"])

    assert cache.load_hashed(object(), "ttl-key") == api_key_cache.ApiKeyAuthMetadata(org_id=9)

    durable_version["value"] = "2"
    fake_clock.advance(api_key_cache._LOCAL_CACHE_MAX_AGE_SECONDS + 1)

    assert cache.load_hashed(object(), "ttl-key") == api_key_cache.ApiKeyAuthMetadata(org_id=9)
    assert fake_redis.get("ezrules:api_key_auth_version:9") == "2"
    assert load_calls == ["ttl-key", "ttl-key"]


def test_evaluate_reuses_cached_api_key_auth_until_revoke(session, org, live_api_key, monkeypatch):
    shared_redis = FakeRedis()
    shared_cache = api_key_cache.ApiKeyAuthCache(client_getter=lambda: shared_redis)
    load_calls: list[str] = []
    original_loader = api_key_cache._load_api_key_auth_metadata_from_db
    bearer_token = _create_api_key_manager_token(session, org)
    api_key_gid = session.query(ApiKey.gid).filter(ApiKey.o_id == org.o_id, ApiKey.revoked_at.is_(None)).scalar()
    assert api_key_gid is not None

    def _counted_load(db, key_hash: str) -> api_key_cache.ApiKeyAuthMetadata | None:
        load_calls.append(key_hash)
        return original_loader(db, key_hash)

    monkeypatch.setattr(api_key_cache, "_load_api_key_auth_metadata_from_db", _counted_load)
    monkeypatch.setattr(api_key_cache, "_should_use_shared_cache", lambda: True)
    monkeypatch.setattr(api_key_cache, "get_api_key_auth_cache", lambda: shared_cache)

    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)

    with TestClient(app) as client:
        first_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "api_key_cache_eval_1",
                "event_timestamp": 1700000000,
                "event_data": {},
            },
            headers={"X-API-Key": live_api_key},
        )
        second_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "api_key_cache_eval_2",
                "event_timestamp": 1700000001,
                "event_data": {},
            },
            headers={"X-API-Key": live_api_key},
        )
        revoke_response = client.delete(
            f"/api/v2/api-keys/{api_key_gid}",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        revoked_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "api_key_cache_eval_3",
                "event_timestamp": 1700000002,
                "event_data": {},
            },
            headers={"X-API-Key": live_api_key},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert revoke_response.status_code == 204
    assert revoked_response.status_code == 401
    assert load_calls == [
        hashlib.sha256(live_api_key.encode()).hexdigest(),
        hashlib.sha256(live_api_key.encode()).hexdigest(),
    ]
