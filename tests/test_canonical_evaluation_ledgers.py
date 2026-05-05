import datetime

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
    TransactionCurrentVersion,
    User,
)
from tests.canonical_helpers import add_served_decision


def _timestamp(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return int(value.timestamp())


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
                json={"transaction_id": "txn-123", "effective_at": 1710000000, "event_data": {"amount": 10}},
                headers={"X-API-Key": api_key},
            )
            second = client.post(
                "/api/v2/evaluate",
                json={"transaction_id": "txn-123", "effective_at": 1710000300, "event_data": {"amount": 25}},
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["transaction_id"] == "txn-123"
    assert first.json()["event_version"] == 1
    assert first.json()["event_version_id"] is not None
    assert first.json()["evaluation_id"] is not None
    assert first.json()["evaluation_status"] == "new"
    assert second.json()["event_version"] == 2
    assert second.json()["evaluation_status"] == "superseding"
    assert first.json()["evaluation_id"] != second.json()["evaluation_id"]

    versions = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == 1, EventVersion.transaction_id == "txn-123")
        .order_by(EventVersion.event_version.asc())
        .all()
    )
    assert [version.event_version for version in versions] == [1, 2]
    assert versions[0].supersedes_ev_id is None
    assert versions[1].supersedes_ev_id == versions[0].ev_id
    assert versions[1].event_data == {"amount": 25}

    decisions = (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == 1, EvaluationDecision.transaction_id == "txn-123")
        .order_by(EvaluationDecision.event_version.asc())
        .all()
    )
    assert [decision.event_version for decision in decisions] == [1, 2]
    assert all(decision.served for decision in decisions)
    assert all(decision.decision_type == "served" for decision in decisions)
    assert all(decision.rule_config_label == "production" for decision in decisions)
    assert [decision.is_current for decision in decisions] == [False, True]
    assert decisions[0].superseded_by_ed_id == decisions[1].ed_id

    current = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == 1, TransactionCurrentVersion.transaction_id == "txn-123")
        .one()
    )
    assert current.current_ed_id == decisions[1].ed_id
    assert current.first_effective_at == versions[0].effective_at
    assert current.first_observed_at == versions[0].observed_at
    assert current.current_effective_at == versions[1].effective_at
    assert current.current_observed_at == versions[1].observed_at

    rule_results = session.query(EvaluationRuleResult).filter(EvaluationRuleResult.ed_id == decisions[-1].ed_id).all()
    assert [(result.r_id, result.rule_result) for result in rule_results] == [(rule.r_id, "HOLD")]


def test_exact_duplicate_submission_reuses_existing_evaluation_without_new_version(session, ledger_api_key):
    api_key, _token = ledger_api_key
    _save_production_rule(session)
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    payload = {"transaction_id": "txn-dupe", "effective_at": 1710000000, "event_data": {"amount": 10}}
    try:
        with TestClient(app) as client:
            first = client.post("/api/v2/evaluate", json=payload, headers={"X-API-Key": api_key})
            projection = (
                session.query(TransactionCurrentVersion)
                .filter(TransactionCurrentVersion.o_id == 1, TransactionCurrentVersion.transaction_id == "txn-dupe")
                .one()
            )
            first_effective_at = projection.first_effective_at
            first_observed_at = projection.first_observed_at
            current_effective_at = projection.current_effective_at
            current_observed_at = projection.current_observed_at
            duplicate = client.post("/api/v2/evaluate", json=payload, headers={"X-API-Key": api_key})
    finally:
        evaluator_module._lre = None

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["evaluation_status"] == "duplicate"
    assert duplicate.json()["event_version"] == first.json()["event_version"]
    assert duplicate.json()["evaluation_id"] == first.json()["evaluation_id"]
    session.refresh(projection)
    assert projection.first_effective_at == first_effective_at
    assert projection.first_observed_at == first_observed_at
    assert projection.current_effective_at == current_effective_at
    assert projection.current_observed_at == current_observed_at

    assert (
        session.query(EventVersion).filter(EventVersion.o_id == 1, EventVersion.transaction_id == "txn-dupe").count()
        == 1
    )
    assert (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == 1, EvaluationDecision.transaction_id == "txn-dupe")
        .count()
        == 1
    )


def test_same_payload_with_new_observed_time_creates_new_observed_version(session, ledger_api_key):
    api_key, _token = ledger_api_key
    _save_production_rule(session)
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    first_payload = {
        "transaction_id": "txn-observed-replay",
        "effective_at": 1710000000,
        "observed_at": 1710000001,
        "event_data": {"amount": 10},
    }
    replay_payload = {**first_payload, "observed_at": 1710000300}
    try:
        with TestClient(app) as client:
            first = client.post("/api/v2/evaluate", json=first_payload, headers={"X-API-Key": api_key})
            replay = client.post("/api/v2/evaluate", json=replay_payload, headers={"X-API-Key": api_key})
    finally:
        evaluator_module._lre = None

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["evaluation_status"] == "new"
    assert replay.json()["evaluation_status"] == "superseding"
    assert replay.json()["event_version"] == 2
    assert replay.json()["evaluation_id"] != first.json()["evaluation_id"]

    projection = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == 1, TransactionCurrentVersion.transaction_id == "txn-observed-replay")
        .one()
    )
    assert _timestamp(projection.first_effective_at) == 1710000000
    assert _timestamp(projection.first_observed_at) == 1710000001
    assert _timestamp(projection.current_effective_at) == 1710000000
    assert _timestamp(projection.current_observed_at) == 1710000300
    assert (
        session.query(EventVersion)
        .filter(EventVersion.o_id == 1, EventVersion.transaction_id == "txn-observed-replay")
        .count()
        == 2
    )


def test_late_arriving_update_is_stored_but_does_not_replace_current_projection(session, ledger_api_key):
    api_key, _token = ledger_api_key
    _save_production_rule(session)
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    try:
        with TestClient(app) as client:
            current = client.post(
                "/api/v2/evaluate",
                json={
                    "transaction_id": "txn-late",
                    "effective_at": 1710000300,
                    "observed_at": 1710000301,
                    "event_data": {"amount": 30},
                },
                headers={"X-API-Key": api_key},
            )
            late = client.post(
                "/api/v2/evaluate",
                json={
                    "transaction_id": "txn-late",
                    "effective_at": 1710000000,
                    "observed_at": 1710000600,
                    "event_data": {"amount": 20},
                },
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert current.status_code == 200
    assert late.status_code == 200
    assert late.json()["evaluation_status"] == "new"
    assert late.json()["is_current"] is False

    projection = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == 1, TransactionCurrentVersion.transaction_id == "txn-late")
        .one()
    )
    assert projection.current_ed_id == current.json()["evaluation_id"]
    assert _timestamp(projection.current_effective_at) == 1710000300
    assert _timestamp(projection.current_observed_at) == 1710000301
    assert _timestamp(projection.first_effective_at) == 1710000000
    assert _timestamp(projection.first_observed_at) == 1710000301


def test_terminal_current_transaction_blocks_later_non_terminal_supersession(session, ledger_api_key):
    api_key, _token = ledger_api_key
    _save_production_rule(session)
    evaluator_module._lre = LocalRuleExecutorSQL(db=session, o_id=1, label="production")

    try:
        with TestClient(app) as client:
            terminal = client.post(
                "/api/v2/evaluate",
                json={
                    "transaction_id": "txn-terminal",
                    "effective_at": 1710000000,
                    "event_data": {"amount": 10, "state": "settled"},
                    "terminal_state": True,
                },
                headers={"X-API-Key": api_key},
            )
            later = client.post(
                "/api/v2/evaluate",
                json={
                    "transaction_id": "txn-terminal",
                    "effective_at": 1710000900,
                    "event_data": {"amount": 11, "state": "pending-correction"},
                },
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert terminal.status_code == 200
    assert later.status_code == 200
    assert terminal.json()["is_current"] is True
    assert later.json()["evaluation_status"] == "new"
    assert later.json()["is_current"] is False

    projection = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == 1, TransactionCurrentVersion.transaction_id == "txn-terminal")
        .one()
    )
    assert projection.terminal_state is True
    assert projection.current_ed_id == terminal.json()["evaluation_id"]


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
                json={"transaction_id": "rollout-ledger", "effective_at": 1710000000, "event_data": {"amount": 99}},
                headers={"X-API-Key": api_key},
            )
    finally:
        evaluator_module._lre = None

    assert response.status_code == 200
    decision_id = response.json()["evaluation_id"]

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
        transaction_id="TestEvent_cascade_result_logs",
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
