import hashlib
import json
from datetime import UTC, datetime

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import EventVersion, FeatureDefinition, Organisation, Role, Rule, User


def _feature_payload(feature_name: str, *, name: str | None = None) -> dict:
    return {
        "name": name or feature_name,
        "entity": "sender",
        "feature_name": feature_name,
        "entity_key": "sender_id",
        "aggregation_type": "sum",
        "source_field": "amount",
        "window_seconds": 86400,
    }


def _graph_feature_payload() -> dict:
    return {
        "name": "User unique cards through graph 90d",
        "entity": "user",
        "feature_name": "unique_cards_graph_90d",
        "feature_kind": "graph",
        "entity_key": "user_id",
        "aggregation_type": "graph_distinct_count",
        "window_seconds": 7776000,
        "graph_config": {
            "target_entity": "card",
            "allowed_entity_types": ["user", "account", "card"],
            "max_depth": 3,
            "max_expanded_nodes": 1000,
        },
    }


def _hash_payload(event_data: dict) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@pytest.fixture(scope="function")
def feature_client(session):
    hashed_password = bcrypt.hashpw("featurepass".encode(), bcrypt.gensalt()).decode()
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    role = Role(name="feature_manager", description="Manages computed features", o_id=org.o_id)
    user = User(
        email="feature_user@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="feature_user@example.com",
        o_id=org.o_id,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for action in (
        PermissionAction.VIEW_FEATURES,
        PermissionAction.MODIFY_FEATURES,
        PermissionAction.DELETE_FEATURE,
        PermissionAction.VIEW_RULES,
    ):
        PermissionManager.grant_permission(role.id, action)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(user.o_id))
    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client


def test_create_activate_and_list_feature(feature_client):
    token = feature_client.test_data["token"]
    payload = _feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h")

    create_response = feature_client.post(
        "/api/v2/features",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    feature = create_response.json()["feature"]
    assert feature["available_as"] == "stat[sender.sent_amount_sum_24h]"
    assert feature["status"] == "draft"

    activate_response = feature_client.post(
        f"/api/v2/features/{feature['fd_id']}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["feature"]["status"] == "active"

    list_response = feature_client.get("/api/v2/features", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert list_response.json()["features"][0]["available_as"] == "stat[sender.sent_amount_sum_24h]"


def test_update_feature_duplicate_path_returns_conflict(feature_client):
    token = feature_client.test_data["token"]
    first_response = feature_client.post(
        "/api/v2/features",
        json=_feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h"),
        headers={"Authorization": f"Bearer {token}"},
    )
    second_response = feature_client.post(
        "/api/v2/features",
        json=_feature_payload("sent_count_24h", name="Sender count 24h"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    duplicate_response = feature_client.put(
        f"/api/v2/features/{second_response.json()['feature']['fd_id']}",
        json=_feature_payload("sent_amount_sum_24h", name="Renamed duplicate"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Feature path already exists"


def test_deprecate_referenced_feature_is_rejected(feature_client):
    token = feature_client.test_data["token"]
    session = feature_client.test_data["session"]
    org = feature_client.test_data["org"]
    create_response = feature_client.post(
        "/api/v2/features",
        json=_feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    feature_id = create_response.json()["feature"]["fd_id"]
    activate_response = feature_client.post(
        f"/api/v2/features/{feature_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activate_response.status_code == 200
    session.add(
        Rule(
            logic="if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD",
            description="Hold high 24h sender volume",
            rid="FEATURE:DEPS",
            o_id=org.o_id,
            r_id=9201,
        )
    )
    session.commit()

    deprecate_response = feature_client.post(
        f"/api/v2/features/{feature_id}/deprecate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deprecate_response.status_code == 400
    assert deprecate_response.json()["detail"] == "Feature is used by rules"


def test_deprecate_ignores_comment_only_feature_dependency(feature_client):
    token = feature_client.test_data["token"]
    session = feature_client.test_data["session"]
    org = feature_client.test_data["org"]
    create_response = feature_client.post(
        "/api/v2/features",
        json=_feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    feature_id = create_response.json()["feature"]["fd_id"]
    activate_response = feature_client.post(
        f"/api/v2/features/{feature_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activate_response.status_code == 200
    session.add(
        Rule(
            logic="# stat[sender.sent_amount_sum_24h]\nif $amount > 100:\n\treturn !HOLD",
            description="Comment mentions the feature but rule does not use it",
            rid="FEATURE:COMMENT",
            o_id=org.o_id,
            r_id=9202,
        )
    )
    session.commit()

    deprecate_response = feature_client.post(
        f"/api/v2/features/{feature_id}/deprecate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deprecate_response.status_code == 200
    assert deprecate_response.json()["feature"]["status"] == "deprecated"


def test_feature_payload_rejects_unsupported_event_time_field(feature_client):
    token = feature_client.test_data["token"]
    payload = _feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h")
    payload["event_time_field"] = "created_at"

    response = feature_client.post(
        "/api/v2/features",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "event_time_field"]


def test_graph_feature_allowed_entity_types_use_same_identifier_rules_as_target(feature_client):
    token = feature_client.test_data["token"]
    payload = _graph_feature_payload()
    payload["graph_config"]["allowed_entity_types"] = ["user", "card", "café"]

    unicode_response = feature_client.post(
        "/api/v2/features",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    payload = _graph_feature_payload()
    payload["graph_config"]["allowed_entity_types"] = ["user", "card", "x" * 65]
    long_response = feature_client.post(
        "/api/v2/features",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert unicode_response.status_code == 422
    assert long_response.status_code == 422


def test_rule_test_reports_missing_feature_entity_key(feature_client):
    token = feature_client.test_data["token"]
    create_response = feature_client.post(
        "/api/v2/features",
        json=_feature_payload("sent_amount_sum_24h", name="Sender sent amount 24h"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    feature_id = create_response.json()["feature"]["fd_id"]
    activate_response = feature_client.post(
        f"/api/v2/features/{feature_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activate_response.status_code == 200

    response = feature_client.post(
        "/api/v2/rules/test",
        json={
            "test_json": json.dumps({"amount": 125}),
            "rule_source": "if stat[sender.sent_amount_sum_24h] > 100:\n\tpass",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "missing entity key 'sender_id'" in data["reason"]


def test_rule_verify_requires_active_feature(feature_client):
    token = feature_client.test_data["token"]
    response = feature_client.post(
        "/api/v2/rules/verify",
        json={"rule_source": "if stat[sender.sent_amount_sum_24h] > 100:\n\tpass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["referenced_features"] == ["sender.sent_amount_sum_24h"]
    assert "not active" in data["errors"][0]["message"]


def test_evaluate_computes_sum_feature_as_of_event_time(session, live_api_key):
    org = session.query(Organisation).one()
    feature = FeatureDefinition(
        o_id=org.o_id,
        name="Sender sent amount 24h",
        entity="sender",
        feature_name="sent_amount_sum_24h",
        entity_key="sender_id",
        aggregation_type="sum",
        source_field="amount",
        window_seconds=86400,
        filters=[],
        status="active",
    )
    rule = Rule(
        logic="if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD",
        description="Hold high 24h sender volume",
        rid="FEATURE:001",
        o_id=org.o_id,
        r_id=9101,
    )
    session.add_all([feature, rule])
    for transaction_id, effective_at, event_data in (
        ("prior-1", datetime(2026, 5, 5, 12, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 60}),
        ("prior-2", datetime(2026, 5, 5, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 70}),
        ("future", datetime(2026, 5, 6, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 10000}),
        ("other-sender", datetime(2026, 5, 5, 13, 0, tzinfo=UTC), {"sender_id": "S2", "amount": 10000}),
    ):
        session.add(
            EventVersion(
                o_id=org.o_id,
                transaction_id=transaction_id,
                event_version=1,
                effective_at=effective_at,
                observed_at=effective_at,
                event_data=event_data,
                payload_hash=_hash_payload(event_data),
            )
        )
    session.commit()

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org.o_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/evaluate",
            json={
                "transaction_id": "current",
                "effective_at": "2026-05-06T12:00:00Z",
                "event_data": {"sender_id": "S1", "amount": 5},
            },
            headers={"X-API-Key": live_api_key},
        )

    evaluator_router._lre = None
    assert response.status_code == 200
    assert response.json()["rule_results"]["9101"] == "HOLD"
