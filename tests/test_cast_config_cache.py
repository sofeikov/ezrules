import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend import cast_config_cache
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldTypeConfig, Organisation, Role, Rule, User


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

    def incr(self, key: str) -> int:
        next_value = int(self._values.get(key, "0")) + 1
        self._values[key] = str(next_value)
        return next_value


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture(autouse=True)
def reset_cast_config_state():
    cast_config_cache.reset_cast_config_cache()
    yield
    cast_config_cache.reset_cast_config_cache()
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None


def _setup_rule_engine(session, org: Organisation, rid: str, r_id: int) -> None:
    rule = Rule(logic="return !PASS", description="cast config cache test rule", rid=rid, o_id=org.o_id, r_id=r_id)
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org.o_id).save_config(RDBRuleManager(db=session, o_id=org.o_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)


def _create_field_type_manager_token(session, org: Organisation) -> str:
    hashed_password = bcrypt.hashpw("cachepass".encode(), bcrypt.gensalt()).decode()

    role = session.query(Role).filter(Role.name == "cache_manager", Role.o_id == org.o_id).first()
    if role is None:
        role = Role(name="cache_manager", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "cache-manager@example.com", User.o_id == org.o_id).first()
    if user is None:
        user = User(
            email="cache-manager@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="cache-manager@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.DELETE_FIELD_TYPE)

    return create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(org.o_id))


def test_cast_config_cache_reuses_worker_memory_when_version_is_stable(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    cache = cast_config_cache.CastConfigCache(client_getter=lambda: fake_redis)
    load_calls: list[int] = []
    configs = [
        FieldCastConfig(
            field_name="amount",
            field_type=FieldType.INTEGER,
            datetime_format=None,
            required=False,
        )
    ]

    def _fake_load(db, o_id: int) -> list[FieldCastConfig]:
        del db
        load_calls.append(o_id)
        return configs

    monkeypatch.setattr(cast_config_cache, "_load_cast_configs_from_db", _fake_load)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, o_id: "0")

    assert cache.load(object(), 42) == configs
    assert cache.load(object(), 42) == configs
    assert load_calls == [42]


def test_cast_config_cache_invalidation_refreshes_other_worker(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    worker_one = cast_config_cache.CastConfigCache(client_getter=lambda: fake_redis)
    worker_two = cast_config_cache.CastConfigCache(client_getter=lambda: fake_redis)
    load_calls: list[int] = []
    current_type = FieldType.INTEGER
    durable_version = {"value": "1"}

    def _fake_load(db, o_id: int) -> list[FieldCastConfig]:
        del db
        load_calls.append(o_id)
        return [
            FieldCastConfig(
                field_name="amount",
                field_type=current_type,
                datetime_format=None,
                required=False,
            )
        ]

    monkeypatch.setattr(cast_config_cache, "_load_cast_configs_from_db", _fake_load)
    monkeypatch.setattr(worker_one, "_read_durable_version", lambda db, o_id: durable_version["value"])
    monkeypatch.setattr(worker_two, "_read_durable_version", lambda db, o_id: durable_version["value"])

    assert worker_one.load(object(), 7)[0].field_type == FieldType.INTEGER
    assert worker_two.load(object(), 7)[0].field_type == FieldType.INTEGER

    current_type = FieldType.STRING
    durable_version["value"] = "2"
    assert worker_one.publish(7, 2) is True

    refreshed_configs = worker_two.load(object(), 7)
    assert refreshed_configs[0].field_type == FieldType.STRING
    assert load_calls == [7, 7, 7]


def test_cast_config_cache_recovers_from_redis_key_loss(monkeypatch: pytest.MonkeyPatch):
    fake_redis = FakeRedis()
    fake_clock = FakeMonotonic()
    cache = cast_config_cache.CastConfigCache(client_getter=lambda: fake_redis)
    load_calls: list[int] = []
    durable_version = {"value": "1"}
    current_type = {"value": FieldType.INTEGER}

    def _fake_load(db, o_id: int) -> list[FieldCastConfig]:
        del db
        load_calls.append(o_id)
        return [
            FieldCastConfig(
                field_name="amount",
                field_type=current_type["value"],
                datetime_format=None,
                required=False,
            )
        ]

    monkeypatch.setattr(cast_config_cache, "_load_cast_configs_from_db", _fake_load)
    monkeypatch.setattr(cast_config_cache, "monotonic", fake_clock)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, o_id: durable_version["value"])

    assert cache.load(object(), 3)[0].field_type == FieldType.INTEGER

    fake_redis._values.clear()
    durable_version["value"] = "2"
    current_type["value"] = FieldType.STRING

    refreshed = cache.load(object(), 3)
    assert refreshed[0].field_type == FieldType.STRING
    assert fake_redis.get("ezrules:field_type_config_version:3") == "2"
    assert load_calls == [3, 3]


def test_cast_config_cache_refreshes_from_durable_version_after_ttl_when_redis_publish_was_missed(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = FakeRedis()
    fake_clock = FakeMonotonic()
    cache = cast_config_cache.CastConfigCache(client_getter=lambda: fake_redis)
    load_calls: list[int] = []
    durable_version = {"value": "1"}
    current_type = {"value": FieldType.INTEGER}

    def _fake_load(db, o_id: int) -> list[FieldCastConfig]:
        del db
        load_calls.append(o_id)
        return [
            FieldCastConfig(
                field_name="amount",
                field_type=current_type["value"],
                datetime_format=None,
                required=False,
            )
        ]

    monkeypatch.setattr(cast_config_cache, "_load_cast_configs_from_db", _fake_load)
    monkeypatch.setattr(cast_config_cache, "monotonic", fake_clock)
    monkeypatch.setattr(cache, "_read_durable_version", lambda db, o_id: durable_version["value"])

    assert cache.load(object(), 9)[0].field_type == FieldType.INTEGER

    durable_version["value"] = "2"
    current_type["value"] = FieldType.STRING
    assert cache.load(object(), 9)[0].field_type == FieldType.INTEGER

    fake_clock.advance(cast_config_cache._LOCAL_CACHE_MAX_AGE_SECONDS + 1)

    refreshed = cache.load(object(), 9)
    assert refreshed[0].field_type == FieldType.STRING
    assert fake_redis.get("ezrules:field_type_config_version:9") == "2"
    assert load_calls == [9, 9]


def test_evaluate_reuses_cached_cast_configs_until_field_type_mutation(session, live_api_key, monkeypatch):
    org = session.query(Organisation).one()
    _setup_rule_engine(session, org, "CAST:CACHE:001", 9201)
    session.add(FieldTypeConfig(field_name="ref", configured_type="integer", o_id=org.o_id))
    session.commit()

    shared_redis = FakeRedis()
    shared_cache = cast_config_cache.CastConfigCache(client_getter=lambda: shared_redis)
    load_calls: list[int] = []
    original_loader = cast_config_cache._load_cast_configs_from_db
    field_type_manager_token = _create_field_type_manager_token(session, org)

    def _counted_load(db, o_id: int) -> list[FieldCastConfig]:
        load_calls.append(o_id)
        return original_loader(db, o_id)

    monkeypatch.setattr(cast_config_cache, "_load_cast_configs_from_db", _counted_load)
    monkeypatch.setattr(cast_config_cache, "_should_use_shared_cache", lambda: True)
    monkeypatch.setattr(cast_config_cache, "get_cast_config_cache", lambda: shared_cache)

    with TestClient(app) as client:
        first_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "cast_cache_eval_1",
                "event_timestamp": 1700000000,
                "event_data": {"ref": "123"},
            },
            headers={"X-API-Key": live_api_key},
        )
        second_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "cast_cache_eval_2",
                "event_timestamp": 1700000001,
                "event_data": {"ref": "456"},
            },
            headers={"X-API-Key": live_api_key},
        )
        update_response = client.put(
            "/api/v2/field-types/ref",
            headers={"Authorization": f"Bearer {field_type_manager_token}"},
            json={"configured_type": "string"},
        )
        post_update_response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "cast_cache_eval_3",
                "event_timestamp": 1700000002,
                "event_data": {"ref": "not-a-number"},
            },
            headers={"X-API-Key": live_api_key},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert update_response.status_code == 200
    assert post_update_response.status_code == 200
    assert load_calls == [1, 1]
