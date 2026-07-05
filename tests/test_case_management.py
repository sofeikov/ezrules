import datetime

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.cases import (
    CASE_DECISION_RESCORED_NEUTRAL,
    CASE_STATUS_OPEN,
    CASE_STATUS_RESOLVED,
    CaseConflictError,
    process_evaluation_for_cases,
    resolve_case,
)
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    Case,
    CaseEvent,
    EvaluationDecision,
    EventVersion,
    IntegrationEvent,
    Organisation,
    Role,
    User,
)


def _seed_case_org(session) -> tuple[Organisation, User, str]:
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    for severity_rank, outcome_name in enumerate(("CANCEL", "HOLD", "RELEASE"), start=1):
        if (
            session.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == int(org.o_id), AllowedOutcome.outcome_name == outcome_name)
            .first()
            is None
        ):
            session.add(AllowedOutcome(outcome_name=outcome_name, severity_rank=severity_rank, o_id=int(org.o_id)))

    role = Role(name="case_manager", description="Can manage cases", o_id=int(org.o_id))
    user = User(
        email="case-manager@example.com",
        password="unused",
        active=True,
        fs_uniquifier="case-manager@example.com",
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in (
        PermissionAction.VIEW_CASES,
        PermissionAction.MANAGE_CASES,
        PermissionAction.VIEW_INTEGRATIONS,
        PermissionAction.MANAGE_INTEGRATIONS,
    ):
        PermissionManager.grant_permission(int(role.id), permission)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(org.o_id),
    )
    return org, user, token


def _add_decision(
    session,
    *,
    org_id: int = 1,
    transaction_id: str = "txn-case-1",
    outcome: str | None = "HOLD",
    version: int = 1,
    is_current: bool = True,
) -> EvaluationDecision:
    now = datetime.datetime.now(datetime.UTC)
    event = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=version,
        effective_at=now,
        observed_at=now,
        event_data={"transaction_id": transaction_id, "amount": 100 + version},
        payload_hash=f"{transaction_id}-{version}",
    )
    session.add(event)
    session.flush()
    counters = {outcome: 1} if outcome else {}
    decision = EvaluationDecision(
        ev_id=int(event.ev_id),
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=version,
        effective_at=now,
        observed_at=now,
        decision_type="served",
        served=True,
        is_current=is_current,
        outcome_counters=counters,
        resolved_outcome=outcome,
        all_rule_results={"1": outcome} if outcome else {},
        evaluated_at=now,
    )
    session.add(decision)
    session.flush()
    return decision


def test_case_created_for_non_neutral_decision_and_integration_events(session):
    _seed_case_org(session)
    decision = _add_decision(session, outcome="HOLD")

    result = process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()

    assert result.action == "created"
    case = session.query(Case).one()
    assert case.current_ed_id == decision.ed_id
    assert case.status == CASE_STATUS_OPEN
    assert case.resolved_outcome == "HOLD"
    assert [event.event_type for event in session.query(CaseEvent).all()] == ["created"]
    event_types = {event.event_type for event in session.query(IntegrationEvent).all()}
    assert event_types == {"case.created", "evaluation.completed"}


def test_neutral_decision_only_publishes_evaluation_event(session):
    _seed_case_org(session)
    decision = _add_decision(session, outcome="RELEASE")

    result = process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()

    assert result.case_id is None
    assert session.query(Case).count() == 0
    assert [event.event_type for event in session.query(IntegrationEvent).all()] == ["evaluation.completed"]


def test_rescore_updates_active_case_instead_of_creating_duplicate(session):
    _seed_case_org(session)
    first = _add_decision(session, outcome="HOLD", version=1, is_current=True)
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(first.ed_id))
    first.is_current = False
    second = _add_decision(session, outcome="CANCEL", version=2, is_current=True)

    result = process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(second.ed_id))
    session.commit()

    assert result.action == "rescored"
    assert session.query(Case).count() == 1
    case = session.query(Case).one()
    assert case.current_ed_id == second.ed_id
    assert case.previous_ed_id == first.ed_id
    assert case.previous_resolved_outcome == "HOLD"
    assert case.resolved_outcome == "CANCEL"
    assert [event.event_type for event in session.query(CaseEvent).order_by(CaseEvent.case_event_id)] == [
        "created",
        "rescored",
    ]


def test_rescore_to_neutral_keeps_case_open_with_non_caseable_state(session):
    _seed_case_org(session)
    first = _add_decision(session, outcome="HOLD", version=1, is_current=True)
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(first.ed_id))
    first.is_current = False
    second = _add_decision(session, outcome="RELEASE", version=2, is_current=True)

    result = process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(second.ed_id))
    session.commit()

    assert result.action == "rescored_non_caseable"
    case = session.query(Case).one()
    assert case.current_ed_id == second.ed_id
    assert case.status == CASE_STATUS_OPEN
    assert case.decision_state == CASE_DECISION_RESCORED_NEUTRAL


def test_resolve_requires_current_decision_when_expected_id_is_supplied(session):
    _org, user, _token = _seed_case_org(session)
    first = _add_decision(session, outcome="HOLD", version=1, is_current=True)
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(first.ed_id))
    first.is_current = False
    second = _add_decision(session, outcome="CANCEL", version=2, is_current=True)
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(second.ed_id))
    case = session.query(Case).one()

    with pytest.raises(CaseConflictError):
        resolve_case(
            session,
            o_id=1,
            case_id=int(case.case_id),
            actor_user_id=int(user.id),
            resolution_note="Reviewed before score changed",
            expected_current_ed_id=int(first.ed_id),
        )


def test_cases_and_integration_events_api(session):
    _org, user, token = _seed_case_org(session)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()
    case = session.query(Case).one()

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        list_response = client.get("/api/v2/cases", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["cases"][0]["id"] == int(case.case_id)

        resolve_response = client.post(
            f"/api/v2/cases/{case.case_id}/resolve",
            headers=headers,
            json={
                "resolution_note": "Reviewed customer history and approved closure.",
                "expected_current_ed_id": int(decision.ed_id),
            },
        )
        assert resolve_response.status_code == 200
        assert resolve_response.json()["case"]["status"] == CASE_STATUS_RESOLVED

        events_response = client.get("/api/v2/integration-events", headers=headers)
        assert events_response.status_code == 200
        event_types = [event["event_type"] for event in events_response.json()["events"]]
        assert "evaluation.completed" in event_types
        assert "case.resolved" in event_types

    assert session.query(Case).filter(Case.resolved_by_user_id == int(user.id)).count() == 1
