import bcrypt
import hashlib
from datetime import UTC, datetime

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
from ezrules.models.backend_core import (
    Organisation,
    Role,
    Rule as RuleModel,
    RuleDeploymentResultsLog,
    RuleEngineConfig,
    RuleStatus,
    User,
)


def _stable_bucket(o_id: int, r_id: int, event_id: str) -> int:
    digest = hashlib.sha256(f"{o_id}:{r_id}:{event_id}".encode("utf-8")).hexdigest()
    return int(digest, 16) % 100


def _find_event_id_for_bucket(o_id: int, r_id: int, predicate) -> str:
    for index in range(1, 2000):
        event_id = f"rollout-event-{index}"
        if predicate(_stable_bucket(o_id, r_id, event_id)):
            return event_id
    raise AssertionError("Could not find a matching event id for rollout bucket test")


@pytest.fixture(scope="function")
def rollout_test_client(session):
    hashed_password = bcrypt.hashpw("rolloutpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "rollout_manager").first()
    if not role:
        role = Role(name="rollout_manager", description="Can manage rollouts")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "rolloutuser@example.com").first()
    if not user:
        user = User(
            email="rolloutuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="rolloutuser@example.com",
            o_id=1,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)
    PermissionManager.grant_permission(role.id, PermissionAction.PROMOTE_RULES)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"session": session, "token": token, "user": user}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def active_rollout_rule(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    rule = RuleModel(
        rid="rollout_test_rule",
        logic="return 'CONTROL'",
        description="Rule for rollout testing",
        status=RuleStatus.ACTIVE,
        effective_from=datetime.now(UTC),
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()

    rm = RDBRuleManager(db=session, o_id=org.o_id)
    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    config_producer.save_config(rm)
    return rule


class TestRolloutEndpoints:
    def test_deploy_rule_to_rollout(self, rollout_test_client, active_rollout_rule):
        token = rollout_test_client.test_data["token"]
        session = rollout_test_client.test_data["session"]

        response = rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 25},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True

        rollout_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "rollout", RuleEngineConfig.o_id == 1)
            .first()
        )
        assert rollout_config is not None
        rollout_entry = next(entry for entry in rollout_config.config if entry["r_id"] == active_rollout_rule.r_id)
        assert rollout_entry["logic"] == "return 'CANDIDATE'"
        assert rollout_entry["traffic_percent"] == 25
        assert rollout_entry["control"]["logic"] == "return 'CONTROL'"

    def test_rollout_requires_active_rule(self, rollout_test_client, session):
        token = rollout_test_client.test_data["token"]
        draft_rule = RuleModel(
            rid="draft_rollout_rule",
            logic="return 'DRAFT'",
            description="Draft rule",
            status=RuleStatus.DRAFT,
            o_id=1,
        )
        session.add(draft_rule)
        session.commit()

        response = rollout_test_client.post(
            f"/api/v2/rules/{draft_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Only active rules can be rolled out"

    def test_rollout_conflicts_with_shadow(self, rollout_test_client, active_rollout_rule):
        token = rollout_test_client.test_data["token"]
        session = rollout_test_client.test_data["session"]

        deploy_rule_to_shadow(db=session, o_id=1, rule_model=active_rollout_rule, changed_by="test")

        response = rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert "shadow" in response.json()["detail"]

    def test_promote_rollout_updates_rule_and_production_config(self, rollout_test_client, active_rollout_rule):
        token = rollout_test_client.test_data["token"]
        session = rollout_test_client.test_data["session"]

        rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 40},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout/promote",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        session.expire_all()

        promoted_rule = session.get(RuleModel, active_rollout_rule.r_id)
        assert promoted_rule.logic == "return 'CANDIDATE'"
        assert promoted_rule.description == "Candidate"

        prod_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "production", RuleEngineConfig.o_id == 1)
            .first()
        )
        prod_entry = next(entry for entry in prod_config.config if entry["r_id"] == active_rollout_rule.r_id)
        assert prod_entry["logic"] == "return 'CANDIDATE'"

        rollout_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "rollout", RuleEngineConfig.o_id == 1)
            .first()
        )
        assert rollout_config is not None
        assert all(entry["r_id"] != active_rollout_rule.r_id for entry in rollout_config.config)

    def test_promote_rollout_preserves_main_rule_execution_order(self, rollout_test_client, active_rollout_rule):
        token = rollout_test_client.test_data["token"]
        session = rollout_test_client.test_data["session"]

        active_rollout_rule.execution_order = 2
        leading_rule = RuleModel(
            rid="rollout_leading_rule",
            logic="return 'LEAD'",
            description="Runs first",
            status=RuleStatus.ACTIVE,
            effective_from=datetime.now(UTC),
            execution_order=1,
            o_id=1,
        )
        trailing_rule = RuleModel(
            rid="rollout_trailing_rule",
            logic="return 'TAIL'",
            description="Runs last",
            status=RuleStatus.ACTIVE,
            effective_from=datetime.now(UTC),
            execution_order=3,
            o_id=1,
        )
        session.add_all([leading_rule, trailing_rule])
        session.commit()
        RDBRuleEngineConfigProducer(db=session, o_id=1).save_config(RDBRuleManager(db=session, o_id=1))

        rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 40},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout/promote",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        session.expire_all()

        prod_config = (
            session.query(RuleEngineConfig)
            .filter(RuleEngineConfig.label == "production", RuleEngineConfig.o_id == 1)
            .one()
        )
        assert [entry["r_id"] for entry in prod_config.config] == [
            leading_rule.r_id,
            active_rollout_rule.r_id,
            trailing_rule.r_id,
        ]

    def test_base_rule_update_blocked_while_rollout_active(self, rollout_test_client, active_rollout_rule):
        token = rollout_test_client.test_data["token"]

        rollout_test_client.post(
            f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
            json={"logic": "return 'CANDIDATE'", "description": "Candidate", "traffic_percent": 25},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = rollout_test_client.put(
            f"/api/v2/rules/{active_rollout_rule.r_id}",
            json={"logic": "return 'UPDATED'", "description": "Updated"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert "active rollout deployment" in response.json()["detail"]


class TestRolloutEvaluation:
    def test_rollout_serves_candidate_for_bucketed_event(self, session, active_rollout_rule, live_api_key):
        from ezrules.core.rule_updater import deploy_rule_to_rollout

        evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")
        evaluator_module._shadow_lre = LocalRuleExecutorSQL(db=session, o_id=1, label="shadow")

        deploy_rule_to_rollout(
            db=session,
            o_id=1,
            rule_model=session.get(RuleModel, active_rollout_rule.r_id),
            traffic_percent=10,
            changed_by="test",
            logic_override="return 'CANDIDATE'",
            description_override="Candidate",
        )

        event_id = _find_event_id_for_bucket(1, active_rollout_rule.r_id, lambda bucket: bucket < 10)
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": event_id,
                    "event_timestamp": 1234567890,
                    "event_data": {"amount": 100},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_module._lre = None
        evaluator_module._shadow_lre = None

        assert response.status_code == 200
        assert response.json()["rule_results"][str(active_rollout_rule.r_id)] == "CANDIDATE"

        rollout_log = (
            session.query(RuleDeploymentResultsLog)
            .filter(RuleDeploymentResultsLog.mode == "split", RuleDeploymentResultsLog.r_id == active_rollout_rule.r_id)
            .order_by(RuleDeploymentResultsLog.dr_id.desc())
            .first()
        )
        assert rollout_log is not None
        assert rollout_log.selected_variant == "candidate"
        assert rollout_log.returned_result == "CANDIDATE"

    def test_rollout_percentage_increase_is_monotonic(self, session, active_rollout_rule, live_api_key):
        from ezrules.core.rule_updater import deploy_rule_to_rollout

        event_id = _find_event_id_for_bucket(1, active_rollout_rule.r_id, lambda bucket: 10 <= bucket < 20)

        deploy_rule_to_rollout(
            db=session,
            o_id=1,
            rule_model=active_rollout_rule,
            traffic_percent=10,
            changed_by="test",
            logic_override="return 'CANDIDATE'",
            description_override="Candidate",
        )

        evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")
        evaluator_module._shadow_lre = LocalRuleExecutorSQL(db=session, o_id=1, label="shadow")
        with TestClient(app) as client:
            initial_response = client.post(
                "/api/v2/evaluate",
                json={"event_id": event_id, "event_timestamp": 1234567890, "event_data": {}},
                headers={"X-API-Key": live_api_key},
            )

        deploy_rule_to_rollout(
            db=session,
            o_id=1,
            rule_model=session.get(RuleModel, active_rollout_rule.r_id),
            traffic_percent=20,
            changed_by="test",
            logic_override="return 'CANDIDATE'",
            description_override="Candidate",
        )

        evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")
        evaluator_module._shadow_lre = LocalRuleExecutorSQL(db=session, o_id=1, label="shadow")
        with TestClient(app) as client:
            expanded_response = client.post(
                "/api/v2/evaluate",
                json={"event_id": event_id, "event_timestamp": 1234567891, "event_data": {}},
                headers={"X-API-Key": live_api_key},
            )

        evaluator_module._lre = None
        evaluator_module._shadow_lre = None

        assert initial_response.status_code == 200
        assert expanded_response.status_code == 200
        assert initial_response.json()["rule_results"][str(active_rollout_rule.r_id)] == "CONTROL"
        assert expanded_response.json()["rule_results"][str(active_rollout_rule.r_id)] == "CANDIDATE"

    def test_rollout_candidate_failure_falls_back_to_control(self, session, active_rollout_rule, live_api_key):
        from ezrules.core.rule_updater import deploy_rule_to_rollout

        deploy_rule_to_rollout(
            db=session,
            o_id=1,
            rule_model=active_rollout_rule,
            traffic_percent=100,
            changed_by="test",
            logic_override='return t["missing"]["field"]',
            description_override="Broken candidate",
        )

        evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")
        evaluator_module._shadow_lre = LocalRuleExecutorSQL(db=session, o_id=1, label="shadow")
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={"event_id": "always-candidate", "event_timestamp": 1234567890, "event_data": {}},
                headers={"X-API-Key": live_api_key},
            )

        evaluator_module._lre = None
        evaluator_module._shadow_lre = None

        assert response.status_code == 200
        assert response.json()["rule_results"][str(active_rollout_rule.r_id)] == "CONTROL"

        rollout_log = (
            session.query(RuleDeploymentResultsLog)
            .filter(RuleDeploymentResultsLog.mode == "split", RuleDeploymentResultsLog.r_id == active_rollout_rule.r_id)
            .order_by(RuleDeploymentResultsLog.dr_id.desc())
            .first()
        )
        assert rollout_log is not None
        assert rollout_log.selected_variant == "candidate"
        assert rollout_log.candidate_result is None
        assert rollout_log.returned_result == "CONTROL"
