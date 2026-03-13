"""
Tests for the FastAPI v2 tested-events endpoint.
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
def tested_events_client(session):
    """Create a FastAPI test client with permission to view tested events."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    hashed_password = bcrypt.hashpw("tested-events-pass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = Role(name=f"tested_events_viewer_{uuid.uuid4().hex[:8]}", description="Can view tested events")
    user = User(
        email=f"tested-events-{uuid.uuid4().hex[:8]}@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
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


class TestListTestedEvents:
    """Tests for GET /api/v2/tested-events."""

    def test_returns_recent_events_with_triggered_rules(self, session, tested_events_client):
        org = tested_events_client.test_data["org"]
        token = tested_events_client.test_data["token"]

        session.add_all(
            [
                Rule(logic="return 'HOLD'", description="Always hold", rid="EVENTS:001", o_id=org.o_id, r_id=9101),
                Rule(
                    logic="if $amount >= 1000:\n\treturn 'RELEASE'",
                    description="Release high-value traffic",
                    rid="EVENTS:002",
                    o_id=org.o_id,
                    r_id=9102,
                ),
            ]
        )
        session.commit()
        _save_rule_config(session, org.o_id)

        _store_event(session, org.o_id, "evt-older", 1700000000, {"amount": 250})
        _store_event(session, org.o_id, "evt-latest", 1700000001, {"amount": 2500, "country": "GB"})

        response = tested_events_client.get(
            "/api/v2/tested-events",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["limit"] == 1
        assert len(data["events"]) == 1

        latest_event = data["events"][0]
        assert latest_event["event_id"] == "evt-latest"
        assert latest_event["event_timestamp"] == 1700000001
        assert latest_event["resolved_outcome"] == "HOLD"
        assert latest_event["outcome_counters"] == {"HOLD": 1, "RELEASE": 1}
        assert latest_event["event_data"] == {"amount": 2500, "country": "GB"}
        assert latest_event["triggered_rules"] == [
            {
                "r_id": 9101,
                "rid": "EVENTS:001",
                "description": "Always hold",
                "outcome": "HOLD",
            },
            {
                "r_id": 9102,
                "rid": "EVENTS:002",
                "description": "Release high-value traffic",
                "outcome": "RELEASE",
            },
        ]

    def test_includes_events_without_rule_matches(self, session, tested_events_client):
        org = tested_events_client.test_data["org"]
        token = tested_events_client.test_data["token"]

        session.add(
            Rule(
                logic="if $amount > 10000:\n\treturn 'CANCEL'",
                description="Block very high amounts",
                rid="EVENTS:003",
                o_id=org.o_id,
                r_id=9103,
            )
        )
        session.commit()
        _save_rule_config(session, org.o_id)

        _store_event(session, org.o_id, "evt-no-hit", 1700000100, {"amount": 50})

        response = tested_events_client.get(
            "/api/v2/tested-events",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["event_id"] == "evt-no-hit"
        assert data["events"][0]["resolved_outcome"] is None
        assert data["events"][0]["outcome_counters"] == {}
        assert data["events"][0]["triggered_rules"] == []

    def test_requires_authentication(self, tested_events_client):
        response = tested_events_client.get("/api/v2/tested-events")
        assert response.status_code == 401
