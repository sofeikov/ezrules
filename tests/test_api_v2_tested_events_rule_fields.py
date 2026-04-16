"""
Tests for referenced rule fields in the FastAPI v2 tested-events endpoint.
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
from ezrules.models.backend_core import Organisation, Role, Rule, User


@pytest.fixture(scope="function")
def tested_events_field_client(session):
    """Create a FastAPI test client with permission to view tested events."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    hashed_password = bcrypt.hashpw("tested-events-pass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role = Role(name=f"tested_events_fields_{uuid.uuid4().hex[:8]}", description="Can view tested events")
    user = User(
        email=f"tested-events-fields-{uuid.uuid4().hex[:8]}@example.com",
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


def test_returns_referenced_fields_for_triggered_rules(session, tested_events_field_client):
    org = tested_events_field_client.test_data["org"]
    token = tested_events_field_client.test_data["token"]

    session.add_all(
        [
            Rule(
                logic="if $amount >= 1000:\n\treturn !HOLD",
                description="Hold high-value traffic",
                rid="EVENTS:FIELDS:001",
                o_id=org.o_id,
                r_id=9201,
            ),
            Rule(
                logic="if $country == 'GB':\n\treturn !RELEASE",
                description="Release GB traffic",
                rid="EVENTS:FIELDS:002",
                o_id=org.o_id,
                r_id=9202,
            ),
        ]
    )
    session.commit()
    _save_rule_config(session, org.o_id)

    _store_event(
        session,
        org.o_id,
        "evt-highlight-fields",
        1700000200,
        {"amount": 2500, "country": "GB", "merchant": "ACME"},
    )

    response = tested_events_field_client.get(
        "/api/v2/tested-events",
        headers={"Authorization": f"Bearer {token}"},
        params={"include_referenced_fields": "true"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["events"][0]["event_id"] == "evt-highlight-fields"
    assert data["events"][0]["triggered_rules"] == [
        {
            "r_id": 9201,
            "rid": "EVENTS:FIELDS:001",
            "description": "Hold high-value traffic",
            "outcome": "HOLD",
            "referenced_fields": ["amount"],
        },
        {
            "r_id": 9202,
            "rid": "EVENTS:FIELDS:002",
            "description": "Release GB traffic",
            "outcome": "RELEASE",
            "referenced_fields": ["country"],
        },
    ]
