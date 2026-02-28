"""
Tests for shadow deployment endpoints and evaluation.

Covers:
- Deploy rule to shadow
- Remove rule from shadow
- Promote shadow rule to production
- GET /api/v2/shadow (shadow config overview)
- GET /api/v2/shadow/results (shadow results)
- Shadow evaluation during /api/v2/evaluate
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_module
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_shadow,
)
from ezrules.models.backend_core import Organisation, Role, Rule as RuleModel
from ezrules.models.backend_core import RuleEngineConfig, ShadowResultsLog, User


@pytest.fixture(scope="function")
def shadow_test_client(session):
    """Create a FastAPI test client with MODIFY_RULE + VIEW_RULES permissions."""
    hashed_password = bcrypt.hashpw("shadowpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    shadow_role = session.query(Role).filter(Role.name == "shadow_manager").first()
    if not shadow_role:
        shadow_role = Role(name="shadow_manager", description="Can manage shadow rules")
        session.add(shadow_role)
        session.commit()

    shadow_user = session.query(User).filter(User.email == "shadowuser@example.com").first()
    if not shadow_user:
        shadow_user = User(
            email="shadowuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="shadowuser@example.com",
        )
        shadow_user.roles.append(shadow_role)
        session.add(shadow_user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(shadow_role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(shadow_role.id, PermissionAction.MODIFY_RULE)

    roles = [role.name for role in shadow_user.roles]
    token = create_access_token(
        user_id=int(shadow_user.id),
        email=str(shadow_user.email),
        roles=roles,
    )

    client_data = {
        "user": shadow_user,
        "role": shadow_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def shadow_rule(session):
    """Create a rule in the test org for shadow tests."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    rule = RuleModel(
        rid="shadow_test_rule",
        logic="return 'REVIEW'",
        description="Rule for shadow testing",
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()
    return rule


# =============================================================================
# DEPLOY TO SHADOW
# =============================================================================


class TestDeployToShadow:
    """Tests for POST /api/v2/rules/{id}/shadow."""

    def test_deploy_rule_to_shadow(self, shadow_test_client, shadow_rule):
        """Deploying a rule should create a shadow config entry."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        response = shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify shadow config was created in DB
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        assert shadow_config is not None
        r_ids = [r["r_id"] for r in shadow_config.config]
        assert shadow_rule.r_id in r_ids

    def test_deploy_rule_to_shadow_twice_updates(self, shadow_test_client, shadow_rule):
        """Deploying the same rule twice should update, not duplicate."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )
        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        session.expire_all()
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        matching = [r for r in shadow_config.config if r["r_id"] == shadow_rule.r_id]
        assert len(matching) == 1

    def test_deploy_with_logic_override_stores_draft_not_db_logic(self, shadow_test_client, shadow_rule):
        """Deploying with a logic body should store the provided logic in shadow, leaving rules table unchanged."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        draft_logic = "return 'DRAFT_OUTCOME'"
        original_logic = shadow_rule.logic
        assert draft_logic != original_logic

        response = shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            json={"logic": draft_logic, "description": "My draft"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

        session.expire_all()

        # Shadow config has draft logic
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        shadow_entry = next(r for r in shadow_config.config if r["r_id"] == shadow_rule.r_id)
        assert shadow_entry["logic"] == draft_logic
        assert shadow_entry["description"] == "My draft"

        # Rules table is unchanged
        rule_in_db = session.get(RuleModel, shadow_rule.r_id)
        assert rule_in_db.logic == original_logic

    def test_deploy_nonexistent_rule_returns_404(self, shadow_test_client):
        """Deploying a non-existent rule should return 404."""
        token = shadow_test_client.test_data["token"]

        response = shadow_test_client.post(
            "/api/v2/rules/999999/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# REMOVE FROM SHADOW
# =============================================================================


class TestRemoveFromShadow:
    """Tests for DELETE /api/v2/rules/{id}/shadow."""

    def test_remove_rule_from_shadow(self, shadow_test_client, shadow_rule):
        """After deploying and removing, shadow config should not contain the rule."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        # Deploy first
        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Remove
        response = shadow_test_client.delete(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        session.expire_all()
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        if shadow_config is not None:
            r_ids = [r["r_id"] for r in shadow_config.config]
            assert shadow_rule.r_id not in r_ids

    def test_remove_when_not_in_shadow_is_noop(self, shadow_test_client, shadow_rule):
        """Removing a rule that is not in shadow should succeed (no-op)."""
        token = shadow_test_client.test_data["token"]

        response = shadow_test_client.delete(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# =============================================================================
# PROMOTE FROM SHADOW
# =============================================================================


class TestPromoteFromShadow:
    """Tests for POST /api/v2/rules/{id}/shadow/promote."""

    def test_promote_shadow_rule_to_production(self, shadow_test_client, shadow_rule):
        """Promote should move the rule from shadow into production config and update rules table."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        # Deploy rule to shadow
        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Promote
        response = shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow/promote",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        session.expire_all()

        # Rule should be in production config
        prod_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "production", RuleEngineConfig.o_id == 1)
            .first()
        )
        assert prod_config is not None
        prod_r_ids = [r["r_id"] for r in prod_config.config]
        assert shadow_rule.r_id in prod_r_ids

        # Rule should be removed from shadow config
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        if shadow_config is not None:
            shadow_r_ids = [r["r_id"] for r in shadow_config.config]
            assert shadow_rule.r_id not in shadow_r_ids

        # Rules table should reflect the promoted logic
        refreshed_rule = session.get(RuleModel, shadow_rule.r_id)
        assert refreshed_rule is not None
        assert refreshed_rule.logic == shadow_rule.logic

    def test_promote_updates_rules_table_with_shadow_logic(self, shadow_test_client, shadow_rule):
        """When shadow has different logic (via logic_override), promote must update the rules table."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        shadow_logic = "return 'SHADOW_OUTCOME'"
        original_logic = shadow_rule.logic
        assert shadow_logic != original_logic

        # Deploy with a different (draft) logic
        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow",
            json={"logic": shadow_logic, "description": "Draft description"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Verify shadow has the override logic, rules table still has original
        session.expire_all()
        shadow_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == 1)
            .first()
        )
        shadow_entry = next(r for r in shadow_config.config if r["r_id"] == shadow_rule.r_id)
        assert shadow_entry["logic"] == shadow_logic

        rule_in_db = session.get(RuleModel, shadow_rule.r_id)
        assert rule_in_db.logic == original_logic  # unchanged

        # Promote
        shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow/promote",
            headers={"Authorization": f"Bearer {token}"},
        )

        session.expire_all()

        # Rules table must now have the shadow logic
        promoted_rule = session.get(RuleModel, shadow_rule.r_id)
        assert promoted_rule.logic == shadow_logic
        assert promoted_rule.description == "Draft description"

        # Production config must also have the shadow logic
        prod_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "production", RuleEngineConfig.o_id == 1)
            .first()
        )
        prod_entry = next(r for r in prod_config.config if r["r_id"] == shadow_rule.r_id)
        assert prod_entry["logic"] == shadow_logic

    def test_promote_rule_not_in_shadow_returns_400(self, shadow_test_client, shadow_rule):
        """Promoting a rule that is not in shadow should return 400."""
        token = shadow_test_client.test_data["token"]

        response = shadow_test_client.post(
            f"/api/v2/rules/{shadow_rule.r_id}/shadow/promote",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400


# =============================================================================
# SHADOW CONFIG ENDPOINT
# =============================================================================


class TestShadowConfigEndpoint:
    """Tests for GET /api/v2/shadow."""

    def test_get_shadow_config_empty(self, shadow_test_client):
        """Should return empty config when no shadow rules deployed."""
        token = shadow_test_client.test_data["token"]

        response = shadow_test_client.get(
            "/api/v2/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rules"] == []
        assert data["version"] == 0

    def test_get_shadow_config_with_rules(self, shadow_test_client, shadow_rule):
        """Should return rules after deployment."""
        token = shadow_test_client.test_data["token"]
        session = shadow_test_client.test_data["session"]

        deploy_rule_to_shadow(db=session, o_id=1, rule_model=shadow_rule, changed_by="test")

        response = shadow_test_client.get(
            "/api/v2/shadow",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rules"]) == 1
        assert data["rules"][0]["r_id"] == shadow_rule.r_id
        assert data["rules"][0]["rid"] == shadow_rule.rid


# =============================================================================
# SHADOW EVALUATION
# =============================================================================


class TestShadowEvaluation:
    """Tests for shadow evaluation during POST /api/v2/evaluate."""

    def test_shadow_results_stored_when_shadow_config_exists(self, session, live_api_key):
        """Shadow results log entries should be created when a shadow config exists."""
        org = session.query(Organisation).filter(Organisation.o_id == 1).first()
        if not org:
            org = Organisation(o_id=1, name="Test Org")
            session.add(org)
            session.commit()

        # Create a rule and add to production config
        rule = RuleModel(logic="return 'HOLD'", description="Shadow eval rule", rid="SHADOW_EVAL:001", o_id=org.o_id)
        session.add(rule)
        session.commit()

        rm = RDBRuleManager(db=session, o_id=org.o_id)
        config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        config_producer.save_config(rm)

        # Deploy same rule to shadow as well
        deploy_rule_to_shadow(db=session, o_id=org.o_id, rule_model=rule, changed_by="test")

        # Wire up both executors to the test session
        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id, label="production")
        shadow_lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id, label="shadow")
        evaluator_module._lre = lre
        evaluator_module._shadow_lre = shadow_lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "shadow_eval_test_1",
                    "event_timestamp": 1234567890,
                    "event_data": {"amount": 100},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_module._lre = None
        evaluator_module._shadow_lre = None

        assert response.status_code == 200

        # Verify shadow results were stored
        shadow_logs = session.query(ShadowResultsLog).filter(ShadowResultsLog.r_id == rule.r_id).all()
        assert len(shadow_logs) >= 1
        assert shadow_logs[-1].rule_result == "HOLD"

    def test_no_failure_when_shadow_config_absent(self, session, live_api_key):
        """Main evaluation should succeed even when no shadow config exists."""
        org = session.query(Organisation).filter(Organisation.o_id == 1).first()
        if not org:
            org = Organisation(o_id=1, name="Test Org")
            session.add(org)
            session.commit()

        rule = RuleModel(
            logic="return 'PASS'",
            description="No shadow config rule",
            rid="SHADOW_EVAL:002",
            o_id=org.o_id,
        )
        session.add(rule)
        session.commit()

        rm = RDBRuleManager(db=session, o_id=org.o_id)
        config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        config_producer.save_config(rm)

        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id, label="production")
        shadow_lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id, label="shadow")
        evaluator_module._lre = lre
        evaluator_module._shadow_lre = shadow_lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "shadow_absent_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_module._lre = None
        evaluator_module._shadow_lre = None

        assert response.status_code == 200
