import datetime

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.alerts import detect_alerts_for_outcome
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AlertIncident,
    AlertIncidentCase,
    AlertRule,
    AllowedOutcome,
    Case,
    CaseEvent,
    EvaluationDecision,
    EventVersion,
    InAppNotification,
    Organisation,
    Role,
    User,
)


@pytest.fixture
def alert_case_client(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Alert Case Org")
        session.add(org)
    for rank, name in enumerate(("RELEASE", "CANCEL")):
        if session.query(AllowedOutcome).filter_by(o_id=1, outcome_name=name).first() is None:
            session.add(AllowedOutcome(o_id=1, outcome_name=name, severity_rank=rank))
    role = Role(name="alert_case_reviewer", description="Reviews alert-backed cases", o_id=1)
    user = User(
        email="alert-case@example.com",
        password=bcrypt.hashpw(b"alert-case", bcrypt.gensalt()).decode(),
        active=True,
        fs_uniquifier="alert-case@example.com",
        o_id=1,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_CASES)
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name],
        org_id=1,
    )
    with TestClient(app) as client:
        yield client, token


def _decision(
    session, *, transaction_id: str, evaluated_at: datetime.datetime, outcome: str = "CANCEL"
) -> EvaluationDecision:
    event = EventVersion(
        o_id=1,
        transaction_id=transaction_id,
        event_version=1,
        effective_at=int(evaluated_at.timestamp()),
        event_data={"transaction_id": transaction_id, "amount": 2500},
        payload_hash=f"hash-{transaction_id}",
    )
    session.add(event)
    session.flush()
    decision = EvaluationDecision(
        ev_id=int(event.ev_id),
        o_id=1,
        transaction_id=transaction_id,
        event_version=1,
        effective_at=int(evaluated_at.timestamp()),
        decision_type="served",
        served=True,
        is_current=True,
        outcome_counters={outcome: 1},
        resolved_outcome=outcome,
        all_rule_results={},
        evaluated_at=evaluated_at,
    )
    session.add(decision)
    session.commit()
    return decision


def test_spike_incident_links_matching_decisions_to_reusable_cases(session, alert_case_client):
    client, token = alert_case_client
    now = datetime.datetime.now(datetime.UTC)
    rule = AlertRule(
        o_id=1,
        name="Cancellation surge",
        outcome="CANCEL",
        threshold=1,
        window_seconds=3600,
        cooldown_seconds=1800,
        enabled=True,
    )
    session.add(rule)
    session.commit()
    decisions = [_decision(session, transaction_id=f"spike-{index}", evaluated_at=now) for index in range(2)]

    incident_ids = detect_alerts_for_outcome(session, o_id=1, outcome="CANCEL", now=now)

    assert len(incident_ids) == 1
    incident = session.query(AlertIncident).one()
    links = session.query(AlertIncidentCase).order_by(AlertIncidentCase.aic_id).all()
    assert {int(link.evaluation_decision_id) for link in links} == {int(item.ed_id) for item in decisions}
    assert session.query(Case).count() == 2
    assert session.query(CaseEvent).filter(CaseEvent.event_type == "alert_linked").count() == 2

    first_case_id = int(links[0].case_id)
    detail = client.get(f"/api/v2/cases/{first_case_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert detail.json()["alerts"] == [
        {
            "incident_id": int(incident.ai_id),
            "alert_rule_id": int(rule.ar_id),
            "alert_rule_name": "Cancellation surge",
            "evaluation_decision_id": int(links[0].evaluation_decision_id),
            "outcome": "CANCEL",
            "severity": "critical",
            "observed_count": 2,
            "threshold": 1,
            "window_start": detail.json()["alerts"][0]["window_start"],
            "window_end": detail.json()["alerts"][0]["window_end"],
            "triggered_at": detail.json()["alerts"][0]["triggered_at"],
        }
    ]

    filtered = client.get(
        "/api/v2/cases",
        params={
            "alert_incident_id": int(incident.ai_id),
            "alert_rule_id": int(rule.ar_id),
            "alert_severity": "critical",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2

    unfiltered = client.get(
        "/api/v2/cases?alert_severity=&alerted_from=&alerted_to=",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unfiltered.status_code == 200
    assert unfiltered.json()["total"] == 2
    whitespace_severity = client.get(
        "/api/v2/cases",
        params={"alert_rule_id": int(rule.ar_id), "alert_severity": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert whitespace_severity.status_code == 200
    assert whitespace_severity.json()["total"] == 2

    later_decision = _decision(session, transaction_id="spike-later", evaluated_at=now)
    assert detect_alerts_for_outcome(session, o_id=1, outcome="CANCEL", now=now) == []
    assert session.query(AlertIncidentCase).count() == 3
    session.refresh(incident)
    assert incident.observed_count == 3
    assert incident.window_start == (now - datetime.timedelta(seconds=3600)).replace(tzinfo=None)
    assert incident.window_end == now.replace(tzinfo=None)
    assert (
        session.query(AlertIncidentCase)
        .filter(AlertIncidentCase.evaluation_decision_id == later_decision.ed_id)
        .count()
        == 1
    )
    assert session.query(CaseEvent).filter(CaseEvent.event_type == "alert_linked").count() == 3


def test_alert_case_filters_remain_org_scoped(session, alert_case_client):
    client, token = alert_case_client
    response = client.get(
        "/api/v2/cases",
        params={"alert_incident_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"cases": [], "total": 0}


def test_neutral_spike_notification_falls_back_to_alerts_page(session, alert_case_client):
    now = datetime.datetime.now(datetime.UTC)
    session.add(
        AlertRule(
            o_id=1,
            name="Release volume",
            outcome="RELEASE",
            threshold=1,
            window_seconds=3600,
            cooldown_seconds=1800,
            enabled=True,
        )
    )
    session.commit()
    _decision(session, transaction_id="release-1", evaluated_at=now, outcome="RELEASE")
    _decision(session, transaction_id="release-2", evaluated_at=now, outcome="RELEASE")

    detect_alerts_for_outcome(session, o_id=1, outcome="RELEASE", now=now)

    assert session.query(AlertIncidentCase).count() == 0
    assert session.query(Case).count() == 0
    assert session.query(InAppNotification).one().action_url == "/alerts"
