import datetime

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, Organisation, Role, User
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


@pytest.fixture(scope="function")
def agent_tools_client(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    role = Role(
        name="agent_tools_viewer",
        description="Can use deterministic agent analysis tools",
        o_id=int(org.o_id),
    )
    user = User(
        email="agent-tools@example.com",
        password="agent-tools-pass",
        active=True,
        fs_uniquifier="agent-tools@example.com",
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_LABELS)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[item.name for item in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def agent_tools_fixture(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    fraud_label = Label(label="FRAUD", o_id=int(org.o_id))
    normal_label = Label(label="NORMAL", o_id=int(org.o_id))
    session.add_all([fraud_label, normal_label])
    session.commit()

    rule = RuleModel(
        rid="agent_tools_threshold",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Threshold rule for agent tool analysis",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.commit()

    now = datetime.datetime.now(datetime.UTC)
    records = [
        ("agent_evt_1", 200, "US", fraud_label),
        ("agent_evt_2", 130, "US", normal_label),
        ("agent_evt_3", 80, "GB", normal_label),
        ("agent_evt_4", 170, "GB", fraud_label),
        ("agent_evt_5", 120, "GB", fraud_label),
        ("agent_evt_6", 60, "US", fraud_label),
    ]
    for index, (transaction_id, amount, country, label) in enumerate(records):
        add_served_decision(
            session,
            org_id=int(org.o_id),
            transaction_id=transaction_id,
            event_data={"amount": amount, "country": country},
            evaluated_at=now - datetime.timedelta(minutes=index),
            rule_results={int(rule.r_id): "HOLD"} if amount > 100 else {},
            resolved_outcome="HOLD" if amount > 100 else None,
            label=label,
        )
    session.commit()
    return {"rule": rule}


def test_rule_blast_radius_returns_grouped_flips(agent_tools_client, agent_tools_fixture):
    token = agent_tools_client.test_data["token"]
    rule = agent_tools_fixture["rule"]

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
            "group_by": ["country"],
            "sample_limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["eligible_records"] == 6
    assert data["skipped_records"] == 0
    assert data["stored_result"] == {"HOLD": 4, "NO_OUTCOME": 2}
    assert data["proposed_result"] == {"HOLD": 2, "NO_OUTCOME": 4}
    assert data["outcome_delta"] == {"HOLD": -2, "NO_OUTCOME": 2}
    assert data["changed_decision_count"] == 2
    assert data["changed_decision_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert {event["transaction_id"] for event in data["flipped_events"]} == {"agent_evt_2", "agent_evt_5"}

    groups = {row["group"]["country"]: row for row in data["group_deltas"]}
    assert groups["US"]["changed_decision_count"] == 1
    assert groups["GB"]["changed_decision_count"] == 1


def test_rule_counterexamples_returns_fix_and_regression_buckets(agent_tools_client, agent_tools_fixture):
    token = agent_tools_client.test_data["token"]
    rule = agent_tools_fixture["rule"]

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-counterexamples",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
            "positive_labels": ["FRAUD"],
            "negative_labels": ["NORMAL"],
            "target_outcomes": ["HOLD"],
            "sample_limit": 10,
        },
    )

    assert response.status_code == 200
    buckets = response.json()["buckets"]
    assert {event["transaction_id"] for event in buckets["fired_but_negative"]} == {"agent_evt_2"}
    assert {event["transaction_id"] for event in buckets["missed_positive"]} == {"agent_evt_6"}
    assert {event["transaction_id"] for event in buckets["candidate_fixes_existing"]} == {"agent_evt_2"}
    assert {event["transaction_id"] for event in buckets["candidate_introduces_new_errors"]} == {"agent_evt_5"}


def test_agent_tools_require_label_permission_for_counterexamples(session, agent_tools_fixture):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    role = Role(name="agent_tools_rule_only", description="Can view rules only", o_id=int(org.o_id))
    user = User(
        email="agent-tools-rule-only@example.com",
        password="agent-tools-pass",
        active=True,
        fs_uniquifier="agent-tools-rule-only@example.com",
        o_id=int(org.o_id),
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
        roles=[item.name for item in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agent-tools/rule-counterexamples",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_id": int(agent_tools_fixture["rule"].r_id)},
        )

    assert response.status_code == 403
