import hashlib
import json
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.features import persist_graph_links_for_event
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    EvaluationDecision,
    EventVersion,
    GraphEntityField,
    Organisation,
    Role,
    User,
)


def _hash_payload(event_data: dict) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@pytest.fixture(scope="function")
def graph_client(session):
    hashed_password = bcrypt.hashpw("graphpass".encode(), bcrypt.gensalt()).decode()
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    role = Role(name="graph_viewer", description="Views tested event graphs", o_id=org.o_id)
    user = User(
        email="graph_user@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="graph_user@example.com",
        o_id=org.o_id,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(user.o_id))
    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client


def _configure_graph_fields(session, org_id: int) -> None:
    session.add_all(
        [
            GraphEntityField(o_id=org_id, field_path="user_id", entity_type="user"),
            GraphEntityField(o_id=org_id, field_path="account_id", entity_type="account"),
            GraphEntityField(o_id=org_id, field_path="card_fingerprint", entity_type="card"),
            GraphEntityField(o_id=org_id, field_path="device_id", entity_type="device"),
        ]
    )
    session.commit()


def _add_event(session, org_id: int, transaction_id: str, effective_at: datetime, event_data: dict) -> EventVersion:
    event_version = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1,
        effective_at=effective_at,
        observed_at=effective_at,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
    )
    session.add(event_version)
    session.flush()
    persist_graph_links_for_event(session, org_id, event_version)
    session.commit()
    return event_version


def _add_decision(session, org_id: int, event_version: EventVersion) -> EvaluationDecision:
    decision = EvaluationDecision(
        o_id=org_id,
        ev_id=int(event_version.ev_id),
        transaction_id=str(event_version.transaction_id),
        event_version=int(event_version.event_version),
        effective_at=event_version.effective_at,
        observed_at=event_version.observed_at,
        decision_type="served",
        served=True,
        is_current=True,
        outcome_counters={},
        resolved_outcome=None,
    )
    session.add(decision)
    session.commit()
    return decision


def test_tested_event_graph_returns_root_event_and_entities(graph_client):
    session = graph_client.test_data["session"]
    token = graph_client.test_data["token"]
    org_id = int(graph_client.test_data["org"].o_id)
    _configure_graph_fields(session, org_id)
    event_version = _add_event(
        session,
        org_id,
        "txn-root",
        datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        {"user_id": "user-1", "account_id": "acct-1", "card_fingerprint": "card-1"},
    )
    decision = _add_decision(session, org_id, event_version)

    response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    labels = {node["label"] for node in data["nodes"]}
    assert "txn-root" in labels
    assert "user: user-1" in labels
    assert "account: acct-1" in labels
    assert "card: card-1" in labels
    assert len(data["edges"]) == 3
    assert data["event_count"] == 1
    assert data["truncated"] is False


def test_tested_event_graph_expands_entity_to_linked_events(graph_client):
    session = graph_client.test_data["session"]
    token = graph_client.test_data["token"]
    org_id = int(graph_client.test_data["org"].o_id)
    _configure_graph_fields(session, org_id)
    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    root = _add_event(session, org_id, "txn-root", effective_at, {"user_id": "user-1", "card_fingerprint": "card-1"})
    _add_event(
        session,
        org_id,
        "txn-shared-card",
        effective_at + timedelta(minutes=5),
        {"account_id": "acct-2", "card_fingerprint": "card-1"},
    )
    decision = _add_decision(session, org_id, root)
    root_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    card_node = next(node for node in root_response.json()["nodes"] if node["entity_type"] == "card")

    expanded_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        params={
            "expand_entity_type": card_node["entity_type"],
            "expand_entity_value_hash": card_node["entity_value_hash"],
            "max_events": 10,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert expanded_response.status_code == 200
    labels = {node["label"] for node in expanded_response.json()["nodes"]}
    assert {"txn-root", "txn-shared-card", "account: acct-2", "card: card-1"}.issubset(labels)
    assert expanded_response.json()["event_count"] == 2


def test_tested_event_graph_defaults_to_three_hop_network(graph_client):
    session = graph_client.test_data["session"]
    token = graph_client.test_data["token"]
    org_id = int(graph_client.test_data["org"].o_id)
    _configure_graph_fields(session, org_id)
    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    root = _add_event(session, org_id, "txn-root", effective_at, {"user_id": "user-1", "card_fingerprint": "card-1"})
    _add_event(
        session,
        org_id,
        "txn-hop-1",
        effective_at + timedelta(minutes=1),
        {"card_fingerprint": "card-1", "device_id": "device-1"},
    )
    _add_event(
        session,
        org_id,
        "txn-hop-2",
        effective_at + timedelta(minutes=2),
        {"device_id": "device-1", "account_id": "acct-1"},
    )
    _add_event(
        session,
        org_id,
        "txn-hop-3",
        effective_at + timedelta(minutes=3),
        {"account_id": "acct-1", "user_id": "user-4"},
    )
    decision = _add_decision(session, org_id, root)

    response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    labels = {node["label"] for node in data["nodes"]}
    assert {"txn-root", "txn-hop-1", "txn-hop-2", "txn-hop-3"}.issubset(labels)
    assert data["max_hops"] == 3
    assert data["event_count"] == 4


def test_tested_event_graph_expansion_respects_event_cap(graph_client):
    session = graph_client.test_data["session"]
    token = graph_client.test_data["token"]
    org_id = int(graph_client.test_data["org"].o_id)
    _configure_graph_fields(session, org_id)
    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    root = _add_event(session, org_id, "txn-root", effective_at, {"user_id": "user-1", "card_fingerprint": "card-1"})
    _add_event(session, org_id, "txn-linked-1", effective_at + timedelta(minutes=1), {"card_fingerprint": "card-1"})
    _add_event(session, org_id, "txn-linked-2", effective_at + timedelta(minutes=2), {"card_fingerprint": "card-1"})
    decision = _add_decision(session, org_id, root)
    root_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    card_node = next(node for node in root_response.json()["nodes"] if node["entity_type"] == "card")

    expanded_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        params={
            "expand_entity_type": card_node["entity_type"],
            "expand_entity_value_hash": card_node["entity_value_hash"],
            "max_events": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert expanded_response.status_code == 200
    assert expanded_response.json()["event_count"] <= 2
    assert expanded_response.json()["truncated"] is True


def test_tested_event_graph_does_not_cross_orgs(graph_client):
    session = graph_client.test_data["session"]
    token = graph_client.test_data["token"]
    org_id = int(graph_client.test_data["org"].o_id)
    other_org = Organisation(name="other-graph-org")
    session.add(other_org)
    session.commit()
    other_org_id = int(other_org.o_id)
    _configure_graph_fields(session, org_id)
    _configure_graph_fields(session, other_org_id)
    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    root = _add_event(session, org_id, "txn-root", effective_at, {"user_id": "user-1", "card_fingerprint": "card-1"})
    _add_event(
        session, other_org_id, "txn-other-org", effective_at, {"user_id": "other-user", "card_fingerprint": "card-1"}
    )
    decision = _add_decision(session, org_id, root)
    root_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    card_node = next(node for node in root_response.json()["nodes"] if node["entity_type"] == "card")

    expanded_response = graph_client.get(
        f"/api/v2/tested-events/{decision.ed_id}/graph",
        params={
            "expand_entity_type": card_node["entity_type"],
            "expand_entity_value_hash": card_node["entity_value_hash"],
            "max_events": 10,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    labels = {node["label"] for node in expanded_response.json()["nodes"]}
    assert "txn-other-org" not in labels
    assert "other-user" not in labels
