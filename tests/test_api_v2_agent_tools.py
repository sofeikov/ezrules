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
    assert data["changed_rule_outcome_count"] == 2
    assert data["changed_rule_outcome_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert {event["transaction_id"] for event in data["flipped_events"]} == {"agent_evt_2", "agent_evt_5"}

    groups = {row["group"]["country"]: row for row in data["group_deltas"]}
    assert groups["US"]["changed_rule_outcome_count"] == 1
    assert groups["GB"]["changed_rule_outcome_count"] == 1


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
        blast_response = client.post(
            "/api/v2/agent-tools/rule-blast-radius",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_id": int(agent_tools_fixture["rule"].r_id),
                "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
                "sample_limit": 10,
            },
        )
        response = client.post(
            "/api/v2/agent-tools/rule-counterexamples",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_id": int(agent_tools_fixture["rule"].r_id)},
        )

    assert blast_response.status_code == 200
    assert blast_response.json()["flipped_events"]
    assert all(event["label_name"] is None for event in blast_response.json()["flipped_events"])
    assert response.status_code == 403


def test_rule_blast_radius_ignores_superseded_transaction_versions(
    session,
    agent_tools_client,
    agent_tools_fixture,
):
    token = agent_tools_client.test_data["token"]
    org = agent_tools_client.test_data["org"]
    rule = agent_tools_fixture["rule"]
    normal_label = session.query(Label).filter(Label.o_id == int(org.o_id), Label.label == "NORMAL").one()
    now = datetime.datetime.now(datetime.UTC)

    add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="agent_rescore",
        event_data={"amount": 130, "country": "US"},
        evaluated_at=now - datetime.timedelta(minutes=20),
        rule_results={int(rule.r_id): "HOLD"},
        resolved_outcome="HOLD",
        label=normal_label,
    )
    add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="agent_rescore",
        event_data={"amount": 80, "country": "US"},
        evaluated_at=now - datetime.timedelta(minutes=1),
        rule_results={},
        resolved_outcome=None,
        label=normal_label,
    )
    session.commit()

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
            "sample_limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["eligible_records"] == 7
    assert data["changed_rule_outcome_count"] == 2
    assert {event["transaction_id"] for event in data["flipped_events"]} == {"agent_evt_2", "agent_evt_5"}


def test_rule_blast_radius_returns_404_when_rule_not_found(agent_tools_client):
    token = agent_tools_client.test_data["token"]

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": 999_999,
            "proposed_logic": "return !HOLD",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Rule not found"


def test_rule_blast_radius_rejects_invalid_proposed_logic(agent_tools_client, agent_tools_fixture):
    token = agent_tools_client.test_data["token"]
    rule = agent_tools_fixture["rule"]

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": "if $amount >",
        },
    )

    assert response.status_code == 400
    assert "Invalid proposed rule logic" in response.json()["detail"]


def test_rule_blast_radius_handles_empty_replay_window(session, agent_tools_client):
    token = agent_tools_client.test_data["token"]
    org = agent_tools_client.test_data["org"]
    rule = RuleModel(
        rid="agent_tools_empty_window",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Rule without recent decisions",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.commit()

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 0
    assert data["eligible_records"] == 0
    assert data["changed_rule_outcome_count"] == 0
    assert data["flipped_events"] == []


def test_rule_blast_radius_skips_runtime_key_errors(session, agent_tools_client):
    token = agent_tools_client.test_data["token"]
    org = agent_tools_client.test_data["org"]
    rule = RuleModel(
        rid="agent_tools_runtime_key_error",
        logic='if t["missing"]:\n\treturn !HOLD',
        description="Rule with dynamic missing-key access",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.commit()
    add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="agent_missing_key",
        event_data={"amount": 200},
        rule_results={},
        resolved_outcome=None,
    )
    session.commit()

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": 'if t["missing"]:\n\treturn !HOLD',
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 1
    assert data["eligible_records"] == 0
    assert data["skipped_records"] == 1
    assert data["warnings"] == ["Records missing referenced fields were skipped: missing (1)."]


def test_rule_counterexamples_respects_empty_label_sets(agent_tools_client, agent_tools_fixture):
    token = agent_tools_client.test_data["token"]
    rule = agent_tools_fixture["rule"]

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-counterexamples",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "positive_labels": [],
            "negative_labels": [],
            "sample_limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["positive_labels"] == []
    assert data["negative_labels"] == []
    assert data["buckets"] == {
        "fired_but_negative": [],
        "missed_positive": [],
        "candidate_fixes_existing": [],
        "candidate_introduces_new_errors": [],
    }
