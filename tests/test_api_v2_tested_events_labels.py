"""
Tests for label exposure in the FastAPI v2 tested-events endpoint.
"""

import uuid

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import EventVersion, EventVersionLabel, Label, Organisation, Role, User


@pytest.fixture(scope="function")
def tested_events_client(session):
    """Create a FastAPI test client with permission to view tested events."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    hashed_password = bcrypt.hashpw("tested-events-pass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = Role(name=f"tested_events_labels_{uuid.uuid4().hex[:8]}", description="Can view tested events")
    user = User(
        email=f"tested-events-labels-{uuid.uuid4().hex[:8]}@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=1,
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

    with TestClient(app) as client:
        client.test_data = {"token": token, "org": org}  # type: ignore[attr-defined]
        yield client


def _save_rule_config(session, org_id: int) -> None:
    rule_manager = RDBRuleManager(db=session, o_id=org_id)
    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
    config_producer.save_config(rule_manager)


def _store_event(session, org_id: int, event_id: str, event_timestamp: int, event_data: dict) -> None:
    executor = LocalRuleExecutorSQL(db=session, o_id=org_id)
    eval_and_store(
        executor,
        Event(
            event_id=event_id,
            event_timestamp=event_timestamp,
            event_data=event_data,
        ),
    )


def test_returns_uploaded_label_name_for_labeled_events(session, tested_events_client):
    org = tested_events_client.test_data["org"]
    token = tested_events_client.test_data["token"]

    label = Label(label=f"E2E_LABEL_{uuid.uuid4().hex[:8]}", o_id=org.o_id)
    session.add(label)
    session.commit()

    _save_rule_config(session, org.o_id)

    _store_event(session, org.o_id, "evt-labeled", 1700000200, {"amount": 125, "country": "US"})
    _store_event(session, org.o_id, "evt-unlabeled", 1700000201, {"amount": 90, "country": "GB"})

    labeled_version = (
        session.query(EventVersion)
        .filter(
            EventVersion.o_id == org.o_id,
            EventVersion.event_id == "evt-labeled",
        )
        .one()
    )
    session.add(EventVersionLabel(o_id=org.o_id, ev_id=labeled_version.ev_id, el_id=label.el_id))
    session.commit()

    response = tested_events_client.get(
        "/api/v2/tested-events",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["events"]) == 2

    latest_event = data["events"][0]
    older_event = data["events"][1]

    assert latest_event["event_id"] == "evt-unlabeled"
    assert latest_event["label_name"] is None

    assert older_event["event_id"] == "evt-labeled"
    assert older_event["label_name"] == label.label
