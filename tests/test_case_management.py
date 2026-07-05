import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.cases import (
    CASE_DECISION_RESCORED_NEUTRAL,
    CASE_STATUS_OPEN,
    CASE_STATUS_RESOLVED,
    CaseConflictError,
    CaseValidationError,
    process_evaluation_for_cases,
    resolve_case,
)
from ezrules.backend.integrations import (
    OUTBOX_DELIVERED,
    OUTBOX_SKIPPED,
    dispatch_pending_outbox,
    publish_integration_event,
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
    IntegrationOutbox,
    IntegrationSubscription,
    Label,
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


def test_neutral_decision_matching_is_case_insensitive(session):
    _seed_case_org(session)
    decision = _add_decision(session, outcome="release")

    result = process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()

    assert result.case_id is None
    assert session.query(Case).count() == 0


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


def test_case_assignment_api_records_timeline_events(session):
    _org, user, token = _seed_case_org(session)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()
    case = session.query(Case).one()

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        assign_response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers=headers,
            json={"assigned_to_user_id": int(user.id)},
        )
        assert assign_response.status_code == 200
        assert assign_response.json()["case"]["assigned_to_user_id"] == int(user.id)
        assert assign_response.json()["case"]["status"] == "in_review"

        same_assign_response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers=headers,
            json={"assigned_to_user_id": int(user.id)},
        )
        assert same_assign_response.status_code == 200
        assert same_assign_response.json()["case"]["assigned_to_user_id"] == int(user.id)

        no_op_response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers=headers,
            json={},
        )
        assert no_op_response.status_code == 200
        assert no_op_response.json()["case"]["assigned_to_user_id"] == int(user.id)

        unassign_response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers=headers,
            json={"assigned_to_user_id": None},
        )
        assert unassign_response.status_code == 200
        assert unassign_response.json()["case"]["assigned_to_user_id"] is None
        assert unassign_response.json()["case"]["status"] == "open"

    events = session.query(CaseEvent).order_by(CaseEvent.case_event_id).all()
    assert [event.event_type for event in events] == ["created", "assigned", "assigned"]
    assert events[-2].details["assigned_to_user_id"] == int(user.id)
    assert events[-1].details["assigned_to_user_id"] is None


def test_case_assignment_rejects_user_from_another_org(session):
    _org, _user, token = _seed_case_org(session)
    other_org = Organisation(name="Other org")
    session.add(other_org)
    session.flush()
    other_user = User(
        email="other-case-manager@example.com",
        password="unused",
        active=True,
        fs_uniquifier="other-case-manager@example.com",
        o_id=int(other_org.o_id),
    )
    session.add(other_user)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()
    case = session.query(Case).one()

    with TestClient(app) as client:
        response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"assigned_to_user_id": int(other_user.id)},
        )

    assert response.status_code == 422
    assert session.query(Case).one().assigned_to_user_id is None


def test_case_assignment_rejects_resolved_case(session):
    _org, user, token = _seed_case_org(session)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    case = session.query(Case).one()
    resolve_case(
        session,
        o_id=1,
        case_id=int(case.case_id),
        actor_user_id=int(user.id),
        resolution_note="Already reviewed.",
    )
    session.commit()

    with TestClient(app) as client:
        response = client.patch(
            f"/api/v2/cases/{case.case_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"assigned_to_user_id": int(user.id)},
        )

    assert response.status_code == 422
    assert session.query(Case).one().assigned_to_user_id is None


def test_resolving_already_resolved_case_is_idempotent(session):
    _org, user, _token = _seed_case_org(session)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    case = session.query(Case).one()

    resolve_case(
        session,
        o_id=1,
        case_id=int(case.case_id),
        actor_user_id=int(user.id),
        resolution_note="Reviewed once.",
        expected_current_ed_id=int(decision.ed_id),
    )
    resolve_case(
        session,
        o_id=1,
        case_id=int(case.case_id),
        actor_user_id=int(user.id),
        resolution_note="Reviewed twice.",
        expected_current_ed_id=int(decision.ed_id),
    )
    session.commit()

    assert [event.event_type for event in session.query(CaseEvent).order_by(CaseEvent.case_event_id)] == [
        "created",
        "resolved",
    ]
    assert session.query(IntegrationEvent).filter(IntegrationEvent.event_type == "case.resolved").count() == 1


def test_resolution_label_must_belong_to_case_org(session):
    _org, user, _token = _seed_case_org(session)
    other_org = Organisation(name="Other org")
    session.add(other_org)
    session.flush()
    other_label = Label(label="Other org label", o_id=int(other_org.o_id))
    session.add(other_label)
    decision = _add_decision(session, outcome="HOLD")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    case = session.query(Case).one()

    with pytest.raises(CaseValidationError, match="Resolution label must belong"):
        resolve_case(
            session,
            o_id=1,
            case_id=int(case.case_id),
            actor_user_id=int(user.id),
            resolution_note="Wrong label.",
            resolution_label_id=int(other_label.el_id),
        )


def test_cases_outcome_filter_is_case_insensitive(session):
    _org, _user, token = _seed_case_org(session)
    decision = _add_decision(session, outcome="hold")
    process_evaluation_for_cases(session, o_id=1, evaluation_decision_id=int(decision.ed_id))
    session.commit()

    with TestClient(app) as client:
        response = client.get("/api/v2/cases?outcome=HOLD", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["cases"][0]["resolved_outcome"] == "hold"


def test_integration_subscription_api_validates_webhook_url_and_strips_secret(session):
    _org, _user, token = _seed_case_org(session)

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        invalid_response = client.post(
            "/api/v2/integration-subscriptions",
            headers=headers,
            json={
                "name": "Bad webhook",
                "destination_type": "webhook",
                "config": {"url": "http://example.com/webhook"},
                "event_types": ["case.resolved"],
            },
        )
        assert invalid_response.status_code == 422

        create_response = client.post(
            "/api/v2/integration-subscriptions",
            headers=headers,
            json={
                "name": "Case webhook",
                "destination_type": "webhook",
                "config": {"url": "https://example.com/webhook", "secret": "top-secret"},
                "event_types": ["case.resolved"],
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()["subscription"]
        assert created["config"] == {"url": "https://example.com/webhook"}

        update_response = client.patch(
            f"/api/v2/integration-subscriptions/{created['id']}",
            headers=headers,
            json={
                "name": "Disabled case webhook",
                "config": {"url": "https://events.example.com/cases"},
                "event_types": ["case.created", "case.resolved"],
                "enabled": False,
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()["subscription"]
        assert updated["name"] == "Disabled case webhook"
        assert updated["enabled"] is False
        assert updated["event_types"] == ["case.created", "case.resolved"]
        assert "secret" not in updated["config"]
        stored_subscription = session.query(IntegrationSubscription).one()
        assert stored_subscription.config["secret"] == "top-secret"

        list_response = client.get("/api/v2/integration-subscriptions", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["subscriptions"][0]["id"] == created["id"]


def test_idempotent_integration_publish_enqueues_missing_subscription_delivery(session):
    _seed_case_org(session)
    publish_integration_event(
        session,
        o_id=1,
        source_type="case_event",
        source_id=123,
        event_type="case.created",
        external_event_id="evt_test_case_created",
        payload={"case": {"case_id": 123}},
    )
    session.flush()
    subscription = IntegrationSubscription(
        o_id=1,
        name="Case webhook",
        destination_type="webhook",
        config={"url": "https://example.com/webhook"},
        event_types=["case.created"],
        enabled=True,
    )
    session.add(subscription)
    session.flush()

    result = publish_integration_event(
        session,
        o_id=1,
        source_type="case_event",
        source_id=123,
        event_type="case.created",
        external_event_id="evt_test_case_created",
        payload={"case": {"case_id": 123}},
    )

    assert result.delivery_count == 1
    assert session.query(IntegrationEvent).count() == 1
    assert session.query(IntegrationOutbox).count() == 1


def test_outbox_dispatch_skips_disabled_subscription_delivery(session):
    _seed_case_org(session)
    subscription = IntegrationSubscription(
        o_id=1,
        name="Case webhook",
        destination_type="webhook",
        config={"url": "https://example.com/webhook"},
        event_types=["case.created"],
        enabled=True,
    )
    session.add(subscription)
    session.flush()
    publish_integration_event(
        session,
        o_id=1,
        source_type="case_event",
        source_id=123,
        event_type="case.created",
        external_event_id="evt_test_case_created",
        payload={"case": {"case_id": 123}},
    )
    subscription.enabled = False
    session.commit()

    result = dispatch_pending_outbox(session)

    assert result == {"delivered": 0, "failed": 0}
    delivery = session.query(IntegrationOutbox).one()
    assert delivery.status == OUTBOX_SKIPPED


def test_outbox_dispatch_delivers_webhook_and_marks_delivery(session, monkeypatch):
    _seed_case_org(session)
    subscription = IntegrationSubscription(
        o_id=1,
        name="Case webhook",
        destination_type="webhook",
        config={"url": "https://example.com/webhook", "secret": "top-secret"},
        event_types=["case.created"],
        enabled=True,
    )
    session.add(subscription)
    session.flush()
    publish_integration_event(
        session,
        o_id=1,
        source_type="case_event",
        source_id=123,
        event_type="case.created",
        external_event_id="evt_test_case_created",
        payload={"case": {"case_id": 123}},
    )
    session.commit()

    calls = []

    def fake_post(url, *, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return SimpleNamespace(status_code=204)

    monkeypatch.setattr("ezrules.backend.integrations.requests.post", fake_post)

    result = dispatch_pending_outbox(session)

    assert result == {"delivered": 1, "failed": 0}
    delivery = session.query(IntegrationOutbox).one()
    assert delivery.status == OUTBOX_DELIVERED
    assert delivery.attempt_count == 1
    assert calls[0]["url"] == "https://example.com/webhook"
    assert calls[0]["headers"]["X-Ezrules-Signature"].startswith("sha256=")
