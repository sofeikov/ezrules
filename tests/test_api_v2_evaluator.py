"""
Tests for the FastAPI v2 evaluator endpoint.

These tests verify:
- Event evaluation against rules
- Invalid event handling
- Ping/health check
"""

import hashlib
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import ApiKey, Organisation, Rule


@pytest.fixture(scope="function")
def eval_api_key(session):
    """Create a live API key for evaluate endpoint authentication."""
    org = session.query(Organisation).one()
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="test-eval-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


class TestEvaluate:
    """Tests for POST /api/v2/evaluate."""

    def test_evaluate_event(self, session, eval_api_key):
        """Should evaluate an event against rules and return results."""
        org = session.query(Organisation).one()

        # Create a rule
        rule = Rule(logic="return 'HOLD'", description="Always hold", rid="EVAL_V2:001", o_id=org.o_id, r_id=9001)
        session.add(rule)
        session.commit()

        # Build and save rule engine config
        rm = RDBRuleManager(db=session, o_id=org.o_id)
        config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        config_producer.save_config(rm)

        # Wire up the evaluator's rule executor to use the test session
        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
        evaluator_router._lre = lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "eval_v2_test_1",
                    "event_timestamp": 1234567890,
                    "event_data": {"amount": 500},
                },
                headers={"X-API-Key": eval_api_key},
            )

        evaluator_router._lre = None

        assert response.status_code == 200
        data = response.json()
        assert data["outcome_counters"] == {"HOLD": 1}
        assert data["outcome_set"] == ["HOLD"]
        assert data["rule_results"]["9001"] == "HOLD"

    def test_evaluate_invalid_event(self, session, eval_api_key):
        """Should return 422 for invalid event data."""
        with TestClient(app) as client:
            # Missing required fields
            response = client.post(
                "/api/v2/evaluate",
                json={"event_id": "bad"},
                headers={"X-API-Key": eval_api_key},
            )

        assert response.status_code == 422

    def test_evaluate_invalid_timestamp(self, session, eval_api_key):
        """Should return 422 for out-of-range timestamp."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "ts_test",
                    "event_timestamp": -1,
                    "event_data": {},
                },
                headers={"X-API-Key": eval_api_key},
            )

        assert response.status_code == 422

    def test_evaluate_no_auth_returns_401(self, session):
        """Should return 401 when no credentials are supplied."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "no_auth_test",
                    "event_timestamp": 1234567890,
                    "event_data": {"amount": 100},
                },
            )

        assert response.status_code == 401


class TestPing:
    """Tests for GET /ping."""

    def test_ping(self):
        """Should return ok status."""
        with TestClient(app) as client:
            response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
