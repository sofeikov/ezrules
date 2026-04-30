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
    AlertRule,
    AllowedOutcome,
    EvaluationDecision,
    EventVersion,
    InAppNotification,
    InAppNotificationRead,
    Organisation,
    Role,
    User,
)


@pytest.fixture(scope="function")
def alerts_test_client(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    for severity_rank, outcome_name in enumerate(("CANCEL", "HOLD", "RELEASE"), start=1):
        existing_outcome = (
            session.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == int(org.o_id), AllowedOutcome.outcome_name == outcome_name)
            .first()
        )
        if existing_outcome is None:
            session.add(AllowedOutcome(outcome_name=outcome_name, severity_rank=severity_rank, o_id=int(org.o_id)))
    session.commit()

    role = session.query(Role).filter(Role.name == "alert_manager").first()
    if role is None:
        role = Role(name="alert_manager", description="Can manage alerts", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "alertuser@example.com").first()
    if user is None:
        user = User(
            email="alertuser@example.com",
            password=bcrypt.hashpw("alertpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            active=True,
            fs_uniquifier="alertuser@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ALERTS)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_ALERTS)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "user": user, "org": org, "session": session}  # type: ignore[attr-defined]
        yield client


def _add_decision(session, *, org_id: int, event_id: str, outcome: str, evaluated_at: datetime.datetime) -> None:
    event = EventVersion(
        o_id=org_id,
        event_id=event_id,
        event_version=1,
        event_timestamp=int(evaluated_at.timestamp()),
        event_data={"event_id": event_id},
        payload_hash=event_id,
    )
    session.add(event)
    session.flush()
    session.add(
        EvaluationDecision(
            ev_id=int(event.ev_id),
            o_id=org_id,
            event_id=event_id,
            event_version=1,
            event_timestamp=int(evaluated_at.timestamp()),
            decision_type="served",
            served=True,
            outcome_counters={outcome: 1},
            resolved_outcome=outcome,
            all_rule_results={"1": outcome},
            evaluated_at=evaluated_at,
        )
    )
    session.commit()


def test_create_and_list_alert_rule(alerts_test_client):
    token = alerts_test_client.test_data["token"]

    response = alerts_test_client.post(
        "/api/v2/alerts/rules",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Cancel spike",
            "outcome": "cancel",
            "threshold": 50,
            "window_seconds": 3600,
            "cooldown_seconds": 1800,
            "enabled": True,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["rule"]["outcome"] == "CANCEL"

    list_response = alerts_test_client.get("/api/v2/alerts/rules", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert list_response.json()["rules"][0]["name"] == "Cancel spike"


def test_create_alert_rule_rejects_unknown_outcome(alerts_test_client):
    token = alerts_test_client.test_data["token"]

    response = alerts_test_client.post(
        "/api/v2/alerts/rules",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Unknown spike",
            "outcome": "NOT_CONFIGURED",
            "threshold": 50,
            "window_seconds": 3600,
            "cooldown_seconds": 1800,
            "enabled": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Outcome 'NOT_CONFIGURED' is not configured for this organization"


def test_detect_alert_creates_incident_and_in_app_notification(session):
    now = datetime.datetime.now(datetime.UTC)
    rule = AlertRule(
        o_id=1,
        name="Cancel spike",
        outcome="CANCEL",
        threshold=1,
        window_seconds=3600,
        cooldown_seconds=1800,
        enabled=True,
    )
    session.add(rule)
    session.commit()
    _add_decision(session, org_id=1, event_id="alert-1", outcome="CANCEL", evaluated_at=now)
    _add_decision(session, org_id=1, event_id="alert-2", outcome="CANCEL", evaluated_at=now)

    incident_ids = detect_alerts_for_outcome(session, o_id=1, outcome="CANCEL", now=now)

    assert len(incident_ids) == 1
    incident = session.query(AlertIncident).one()
    assert incident.observed_count == 2
    notification = session.query(InAppNotification).one()
    assert notification.title == "CANCEL spike detected"

    second_incident_ids = detect_alerts_for_outcome(session, o_id=1, outcome="CANCEL", now=now)
    assert second_incident_ids == []


def test_notification_read_state_is_per_user(alerts_test_client):
    token = alerts_test_client.test_data["token"]
    user = alerts_test_client.test_data["user"]
    session = alerts_test_client.test_data["session"]
    session.add(
        InAppNotification(
            o_id=1,
            severity="critical",
            title="CANCEL spike detected",
            body="52 CANCEL decisions in the last 60 minutes.",
            action_url="/alerts",
            source_type="alert_incident",
            source_id=1,
        )
    )
    session.commit()

    unread_response = alerts_test_client.get(
        "/api/v2/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unread_response.status_code == 200
    assert unread_response.json()["unread_count"] == 1

    notification_id = session.query(InAppNotification).one().ian_id
    mark_response = alerts_test_client.post(
        f"/api/v2/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mark_response.status_code == 200
    assert mark_response.json()["unread_count"] == 0
    assert (
        session.query(InAppNotificationRead)
        .filter(InAppNotificationRead.notification_id == notification_id, InAppNotificationRead.user_id == user.id)
        .count()
        == 1
    )
