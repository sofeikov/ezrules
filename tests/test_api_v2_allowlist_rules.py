"""Tests for allowlist rule lane behavior."""

import bcrypt
import hashlib
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    ApiKey,
    Organisation,
    Role,
    RuleStatus,
    RuntimeSetting,
    TestingRecordLog,
    TestingResultsLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel


@pytest.fixture(scope="function")
def allowlist_rules_client(session):
    """Create a test client with rule-management permissions."""
    hashed_password = bcrypt.hashpw("allowlistpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = session.query(Organisation).one()

    role = session.query(Role).filter(Role.name == "allowlist_rule_manager", Role.o_id == org.o_id).first()
    if not role:
        role = Role(name="allowlist_rule_manager", description="Can manage allowlist rules", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "allowlist_rule_manager@example.com").first()
    if not user:
        user = User(
            email="allowlist_rule_manager@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="allowlist_rule_manager@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.CREATE_RULE)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)
    PermissionManager.grant_permission(role.id, PermissionAction.PROMOTE_RULES)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def allowlist_api_key(session):
    """Create a live API key for evaluator requests."""
    org = session.query(Organisation).one()
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="allowlist-eval-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


class TestAllowlistRuleCrud:
    def test_create_rule_accepts_allowlist_lane(self, allowlist_rules_client):
        token = allowlist_rules_client.test_data["token"]

        response = allowlist_rules_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "ALLOWLIST_CREATE_OK",
                "description": "Allowlist release rule",
                "logic": 'if $country == "GB":\n\treturn !RELEASE',
                "evaluation_lane": "allowlist",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["success"] is True
        assert payload["rule"]["evaluation_lane"] == "allowlist"

    def test_create_rule_rejects_non_bypass_allowlist_outcome(self, allowlist_rules_client):
        token = allowlist_rules_client.test_data["token"]

        response = allowlist_rules_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "ALLOWLIST_CREATE_BAD",
                "description": "Invalid allowlist rule",
                "logic": 'if $country == "GB":\n\treturn !HOLD',
                "evaluation_lane": "allowlist",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["success"] is False
        assert "Allowlist rules must return only the configured neutral outcome !RELEASE" in payload["error"]

    def test_create_rule_uses_configured_neutral_outcome(self, allowlist_rules_client):
        token = allowlist_rules_client.test_data["token"]
        session = allowlist_rules_client.test_data["session"]
        org = allowlist_rules_client.test_data["org"]
        session.add(
            RuntimeSetting(
                key="neutral_outcome",
                o_id=int(org.o_id),
                value_type="string",
                value="HOLD",
            )
        )
        session.commit()

        response = allowlist_rules_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "ALLOWLIST_CREATE_HOLD",
                "description": "Allowlist hold rule",
                "logic": 'if $country == "GB":\n\treturn !HOLD',
                "evaluation_lane": "allowlist",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["success"] is True
        assert payload["rule"]["evaluation_lane"] == "allowlist"


class TestAllowlistEvaluation:
    def test_allowlist_hit_short_circuits_main_rules(self, session, allowlist_api_key):
        org = session.query(Organisation).one()
        session.add_all(
            [
                RuleModel(
                    logic='if $country == "GB":\n\treturn !RELEASE',
                    description="Allowlist release for GB",
                    rid="ALLOWLIST_MATCH",
                    evaluation_lane="allowlist",
                    status=RuleStatus.ACTIVE,
                    o_id=org.o_id,
                    r_id=9201,
                ),
                RuleModel(
                    logic="return !HOLD",
                    description="Main rule that would otherwise hold",
                    rid="MAIN_HOLD",
                    evaluation_lane="main",
                    status=RuleStatus.ACTIVE,
                    o_id=org.o_id,
                    r_id=9202,
                ),
            ]
        )
        session.commit()

        config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        config_producer.save_config(RDBRuleManager(db=session, o_id=org.o_id))

        evaluator_router._lre = None
        evaluator_router._shadow_lre = None
        evaluator_router._allowlist_lre = None

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "allowlist-short-circuit",
                    "event_timestamp": 1234567890,
                    "event_data": {"country": "GB"},
                },
                headers={"X-API-Key": allowlist_api_key},
            )

        evaluator_router._lre = None
        evaluator_router._shadow_lre = None
        evaluator_router._allowlist_lre = None

        assert response.status_code == 200
        payload = response.json()
        assert payload["resolved_outcome"] == "RELEASE"
        assert payload["outcome_counters"] == {"RELEASE": 1}
        assert payload["rule_results"] == {"9201": "RELEASE"}

        stored_event = session.query(TestingRecordLog).filter_by(event_id="allowlist-short-circuit").one()
        assert stored_event.resolved_outcome == "RELEASE"
        assert stored_event.outcome_counters == {"RELEASE": 1}

        stored_results = (
            session.query(TestingResultsLog)
            .filter(TestingResultsLog.tl_id == stored_event.tl_id)
            .order_by(TestingResultsLog.r_id.asc())
            .all()
        )
        assert [int(result.r_id) for result in stored_results] == [9201]
        assert [str(result.rule_result) for result in stored_results] == ["RELEASE"]
