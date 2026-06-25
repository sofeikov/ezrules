import datetime
import uuid

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuleStatus, User
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


def _make_client(session, *, grant_view_rules: bool = True) -> tuple[TestClient, str]:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    hashed_password = bcrypt.hashpw("rule-trigger-pass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role = Role(
        name=f"rule_trigger_viewer_{uuid.uuid4().hex[:8]}",
        description="Rule trigger test role",
        o_id=int(org.o_id),
    )
    user = User(
        email=f"rule-trigger-{uuid.uuid4().hex[:8]}@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    if grant_view_rules:
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )

    return TestClient(app), token


def _add_rule(session, *, org_id: int, rid: str) -> RuleModel:
    rule = RuleModel(
        rid=rid,
        logic="return !HOLD",
        description=f"{rid} rule",
        o_id=org_id,
        status=RuleStatus.ACTIVE,
    )
    session.add(rule)
    session.commit()
    return rule


def _ensure_other_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 2).first()
    if org is not None:
        return org

    org = Organisation(o_id=2, name=f"Other Org {uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    return org


def test_rule_triggered_events_pages_and_filters_results(session):
    client, token = _make_client(session)
    target_rule = _add_rule(session, org_id=1, rid=f"TRIGGER_TARGET_{uuid.uuid4().hex[:8]}")
    other_rule = _add_rule(session, org_id=1, rid=f"TRIGGER_OTHER_{uuid.uuid4().hex[:8]}")
    _ensure_other_org(session)
    other_org_rule = _add_rule(session, org_id=2, rid=f"TRIGGER_ORG2_{uuid.uuid4().hex[:8]}")

    base_time = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    for index in range(12):
        add_served_decision(
            session,
            org_id=1,
            transaction_id=f"target-trigger-{index:02d}",
            event_data={"amount": 100 + index, "kind": "target"},
            effective_at=int((base_time + datetime.timedelta(minutes=index)).timestamp()),
            evaluated_at=base_time + datetime.timedelta(minutes=index),
            outcome_counters={"HOLD": 1},
            resolved_outcome="HOLD",
            rule_results={int(target_rule.r_id): "HOLD"},
        )

    add_served_decision(
        session,
        org_id=1,
        transaction_id="other-rule-trigger",
        event_data={"amount": 999, "kind": "same-org-other-rule"},
        rule_results={int(other_rule.r_id): "HOLD"},
        resolved_outcome="HOLD",
    )
    add_served_decision(
        session,
        org_id=1,
        transaction_id="no-rule-trigger",
        event_data={"amount": 1, "kind": "no-hit"},
        rule_results={},
        resolved_outcome=None,
    )
    add_served_decision(
        session,
        org_id=2,
        transaction_id="other-org-trigger",
        event_data={"amount": 1000, "kind": "other-org"},
        rule_results={int(other_org_rule.r_id): "HOLD"},
        resolved_outcome="HOLD",
    )
    session.commit()

    first_page = client.get(
        f"/api/v2/rules/{target_rule.r_id}/triggered-events",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 10, "offset": 0},
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["total"] == 12
    assert first_payload["limit"] == 10
    assert first_payload["offset"] == 0
    assert [event["transaction_id"] for event in first_payload["events"]] == [
        f"target-trigger-{index:02d}" for index in range(11, 1, -1)
    ]
    assert first_payload["events"][0]["triggered_rules"] == [
        {
            "r_id": int(target_rule.r_id),
            "rid": target_rule.rid,
            "description": target_rule.description,
            "outcome": "HOLD",
        }
    ]

    second_page = client.get(
        f"/api/v2/rules/{target_rule.r_id}/triggered-events",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 10, "offset": 10},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["total"] == 12
    assert second_payload["limit"] == 10
    assert second_payload["offset"] == 10
    assert [event["transaction_id"] for event in second_payload["events"]] == [
        "target-trigger-01",
        "target-trigger-00",
    ]


def test_rule_triggered_events_returns_not_found_for_other_org_rule(session):
    client, token = _make_client(session)
    _ensure_other_org(session)
    other_org_rule = _add_rule(session, org_id=2, rid=f"TRIGGER_NOT_FOUND_{uuid.uuid4().hex[:8]}")

    response = client.get(
        f"/api/v2/rules/{other_org_rule.r_id}/triggered-events",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_rule_triggered_events_requires_view_rules_permission(session):
    client, token = _make_client(session, grant_view_rules=False)
    rule = _add_rule(session, org_id=1, rid=f"TRIGGER_FORBIDDEN_{uuid.uuid4().hex[:8]}")

    response = client.get(
        f"/api/v2/rules/{rule.r_id}/triggered-events",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
