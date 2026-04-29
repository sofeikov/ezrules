import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_module
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager, deploy_rule_to_rollout
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    Organisation,
    Role,
    Rule,
    RuleDeploymentResultsLog,
    RuleStatus,
    ShadowResultsLog,
    User,
)
from tests.canonical_helpers import add_served_decision


@pytest.fixture(scope="function")
def ledger_api_key(session, live_api_key):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    role = Role(name="ledger_viewer", description="Can view ledger-backed traffic", o_id=org.o_id)
    user = User(
        email="ledger-viewer@example.com",
        password=bcrypt.hashpw("ledgerpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        active=True,
        fs_uniquifier="ledger-viewer@example.com",
        o_id=org.o_id,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )
    return live_api_key, token


def _save_production_rule(session, *, logic: str = "return !HOLD") -> Rule:
    rule = Rule(
        rid="LEDGER:001",
        logic=logic,
        description="Ledger rule",
        status=RuleStatus.ACTIVE,
        o_id=1,
    )
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=1).save_config(RDBRuleManager(db=session, o_id=1))
    return rule


def test_repeated_business_event_creates_ordered_event_versions_and_served_decisions(session, ledger_api_key):
    api_key, _token = ledger_api_key
    rule = _save_production_rule(session)
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v2/evaluate",
                json={"event_id": "txn-123", "event_timestamp": 1710000000, "event_data": {"amount": 10}},
                headers={"X-API-Key": api_key},
            )
            second = client.post(
                "/api/v2/evaluate",
                json={"event_id": "txn-123", "event_timestamp": 1710000300, "event_data": {"amount": 25}},
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["event_version"] == 1
    assert second.json()["event_version"] == 2
    assert first.json()["evaluation_decision_id"] != second.json()["evaluation_decision_id"]

    versions = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == 1, EventVersion.event_id == "txn-123")
        .order_by(EventVersion.event_version.asc())
        .all()
    )
    assert [version.event_version for version in versions] == [1, 2]
    assert versions[0].supersedes_ev_id is None
    assert versions[1].supersedes_ev_id == versions[0].ev_id
    assert versions[1].event_data == {"amount": 25}

    decisions = (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == 1, EvaluationDecision.event_id == "txn-123")
        .order_by(EvaluationDecision.event_version.asc())
        .all()
    )
    assert [decision.event_version for decision in decisions] == [1, 2]
    assert all(decision.served for decision in decisions)
    assert all(decision.decision_type == "served" for decision in decisions)
    assert all(decision.rule_config_label == "production" for decision in decisions)

    rule_results = session.query(EvaluationRuleResult).filter(EvaluationRuleResult.ed_id == decisions[-1].ed_id).all()
    assert [(result.r_id, result.rule_result) for result in rule_results] == [(rule.r_id, "HOLD")]


def test_rollout_provenance_links_to_the_served_decision(session, ledger_api_key):
    api_key, _token = ledger_api_key
    rule = _save_production_rule(session, logic="return !CONTROL")
    deploy_rule_to_rollout(
        db=session,
        o_id=1,
        rule_model=rule,
        traffic_percent=100,
        changed_by="test",
        logic_override="return !CANDIDATE",
        description_override="Candidate",
    )
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={"event_id": "rollout-ledger", "event_timestamp": 1710000000, "event_data": {"amount": 99}},
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert response.status_code == 200
    decision_id = response.json()["evaluation_decision_id"]

    log = (
        session.query(RuleDeploymentResultsLog)
        .filter(RuleDeploymentResultsLog.ed_id == decision_id, RuleDeploymentResultsLog.r_id == rule.r_id)
        .one()
    )
    assert log.mode == "split"
    assert log.selected_variant == "candidate"
    assert log.returned_result == "CANDIDATE"


def test_event_version_delete_cascades_canonical_result_logs(session):
    rule = _save_production_rule(session)
    decision = add_served_decision(
        session,
        org_id=1,
        event_id="TestEvent_cascade_result_logs",
        event_data={"amount": 42},
        rule_results={int(rule.r_id): "HOLD"},
    )
    session.add_all(
        [
            ShadowResultsLog(ed_id=int(decision.ed_id), r_id=int(rule.r_id), rule_result="HOLD"),
            RuleDeploymentResultsLog(
                ed_id=int(decision.ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="shadow",
                selected_variant="control",
                control_result="HOLD",
                candidate_result="HOLD",
                returned_result="HOLD",
            ),
        ]
    )
    session.commit()

    decision_id = int(decision.ed_id)
    event_version_id = int(decision.ev_id)

    session.query(EventVersion).filter(EventVersion.ev_id == event_version_id).delete(synchronize_session=False)
    session.commit()

    assert session.query(EvaluationDecision).filter(EvaluationDecision.ed_id == decision_id).count() == 0
    assert session.query(ShadowResultsLog).filter(ShadowResultsLog.ed_id == decision_id).count() == 0
    assert session.query(RuleDeploymentResultsLog).filter(RuleDeploymentResultsLog.ed_id == decision_id).count() == 0
