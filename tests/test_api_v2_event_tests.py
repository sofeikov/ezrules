import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import EvaluationDecision, EventVersion, Organisation, Role, User
from ezrules.models.backend_core import Rule as RuleModel


def _event_test_token(session, *, permissions: list[PermissionAction], email: str) -> str:
    org = session.query(Organisation).one()
    role = Role(name=f"event_test_role_{email}", description="Event test role", o_id=int(org.o_id))
    session.add(role)
    session.commit()

    user = User(
        email=email,
        password=bcrypt.hashpw("eventtestpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        active=True,
        fs_uniquifier=email,
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add(user)
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)

    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(user.o_id),
    )


def _save_rule_config(session) -> RuleModel:
    org = session.query(Organisation).one()
    rule = RuleModel(
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Hold high amount events",
        rid="EVENT_TEST_HIGH_AMOUNT",
        o_id=int(org.o_id),
        r_id=9101,
    )
    session.add(rule)
    session.commit()

    rule_manager = RDBRuleManager(db=session, o_id=int(org.o_id))
    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=int(org.o_id))
    config_producer.save_config(rule_manager)
    return rule


def test_event_test_dry_run_returns_rule_set_result_without_persisting(session):
    token = _event_test_token(
        session,
        permissions=[PermissionAction.VIEW_RULES, PermissionAction.SUBMIT_TEST_EVENTS],
        email="event-tester@example.com",
    )
    rule = _save_rule_config(session)
    org = session.query(Organisation).one()
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    evaluator_router._allowlist_lre = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id), label="allowlist")

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/event-tests",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "event_id": "dry_run_event_1",
                    "event_timestamp": 1234567890,
                    "event_data": {"amount": 250},
                },
            )
    finally:
        evaluator_router._lre = None
        evaluator_router._allowlist_lre = None

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["event_version"] is None
    assert payload["evaluation_decision_id"] is None
    assert payload["resolved_outcome"] == "HOLD"
    assert payload["rule_results"] == {str(rule.r_id): "HOLD"}
    assert payload["evaluated_rules"] == [
        {
            "r_id": int(rule.r_id),
            "rid": "EVENT_TEST_HIGH_AMOUNT",
            "description": "Hold high amount events",
            "evaluation_lane": "main",
            "outcome": "HOLD",
            "matched": True,
        }
    ]
    assert session.query(EvaluationDecision).filter(EvaluationDecision.event_id == "dry_run_event_1").count() == 0
    assert session.query(EventVersion).filter(EventVersion.event_id == "dry_run_event_1").count() == 0


def test_event_test_requires_submit_test_events_permission(session):
    token = _event_test_token(
        session,
        permissions=[PermissionAction.VIEW_RULES],
        email="event-test-denied@example.com",
    )
    _save_rule_config(session)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/event-tests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "event_id": "dry_run_denied",
                "event_timestamp": 1234567890,
                "event_data": {"amount": 250},
            },
        )

    assert response.status_code == 403
