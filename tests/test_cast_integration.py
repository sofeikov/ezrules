"""
Integration tests for type casting wired into /evaluate and /rules/test.

Verifies that FieldTypeConfig entries are respected when events are
evaluated and when rules are tested against sample JSON.
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import FieldTypeConfig, Organisation, Role, Rule, User
from ezrules.settings import app_settings


# =============================================================================
# SHARED HELPERS
# =============================================================================


def _get_or_create_org(session):
    """Return the single org created by the conftest session fixture."""
    return session.query(Organisation).one()


def _get_or_create_settings_org(session):
    """Return or create an org whose o_id matches app_settings.ORG_ID.

    The /rules/test endpoint uses app_settings.ORG_ID to load cast configs.
    Postgres sequences do not roll back with transactions, so the org created
    by conftest may have a different o_id; this helper ensures o_id=1 exists.
    """
    org = session.query(Organisation).filter(Organisation.o_id == app_settings.ORG_ID).first()
    if not org:
        org = Organisation(o_id=app_settings.ORG_ID, name="Settings Org")
        session.add(org)
        session.commit()
    return org


def _setup_rule_engine(session, org, rid, r_id):
    """Persist a minimal rule and build the in-memory executor for the test."""
    rule = Rule(logic="return 'PASS'", description="cast integration rule", rid=rid, o_id=org.o_id, r_id=r_id)
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org.o_id).save_config(RDBRuleManager(db=session, o_id=org.o_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
    return rule


@pytest.fixture(scope="function")
def rules_client(session):
    """Authenticated test client with VIEW_RULES permission.

    Uses the org whose o_id matches app_settings.ORG_ID so that FieldTypeConfig
    rows added in tests are visible to the /rules/test endpoint.
    """
    hashed = bcrypt.hashpw("castpass".encode(), bcrypt.gensalt()).decode()

    # /rules/test loads configs keyed by app_settings.ORG_ID; ensure that org exists.
    org = _get_or_create_settings_org(session)

    role = session.query(Role).filter(Role.name == "cast_tester").first()
    if not role:
        role = Role(name="cast_tester")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "cast@example.com").first()
    if not user:
        user = User(email="cast@example.com", password=hashed, active=True, fs_uniquifier="cast@example.com")
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name])

    with TestClient(app) as client:
        client.token = token  # type: ignore[attr-defined]
        client.org = org  # type: ignore[attr-defined]
        yield client


# =============================================================================
# /evaluate casting tests
# =============================================================================


class TestEvaluateCasting:
    """Cast configs should be applied before rule execution in /evaluate."""

    def test_evaluate_casts_string_to_integer(self, session, live_api_key):
        """A string field configured as 'integer' is cast before evaluation."""
        org = _get_or_create_org(session)
        _setup_rule_engine(session, org, "CAST:EVAL:001", 9101)

        config = FieldTypeConfig(field_name="amount", configured_type="integer", o_id=org.o_id)
        session.add(config)
        session.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "cast_eval_1",
                    "event_timestamp": 1700000000,
                    "event_data": {"amount": "500"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None
        assert response.status_code == 200

    def test_evaluate_cast_error_returns_400(self, session, live_api_key):
        """An unparseable value for an integer config must yield HTTP 400."""
        org = _get_or_create_org(session)
        _setup_rule_engine(session, org, "CAST:EVAL:002", 9102)

        config = FieldTypeConfig(field_name="ref", configured_type="integer", o_id=org.o_id)
        session.add(config)
        session.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "cast_eval_2",
                    "event_timestamp": 1700000000,
                    "event_data": {"ref": "not-a-number"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None
        assert response.status_code == 400
        assert "ref" in response.json()["detail"].lower() or "cast" in response.json()["detail"].lower()

    def test_evaluate_unconfigured_field_passes_through(self, session, live_api_key):
        """Fields without a config are passed through unchanged."""
        org = _get_or_create_org(session)
        _setup_rule_engine(session, org, "CAST:EVAL:003", 9103)

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "cast_eval_3",
                    "event_timestamp": 1700000000,
                    "event_data": {"raw_field": "some_string"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None
        assert response.status_code == 200


# =============================================================================
# /rules/test casting tests
# =============================================================================


class TestRulesTestCasting:
    """Cast configs should be applied before rule execution in /rules/test."""

    def test_rules_test_casts_string_to_float(self, rules_client, session):
        """A string field configured as 'float' is cast before rule execution."""
        org = rules_client.org  # type: ignore[attr-defined]
        token = rules_client.token  # type: ignore[attr-defined]

        config = FieldTypeConfig(field_name="score", configured_type="float", o_id=org.o_id)
        session.add(config)
        session.commit()

        response = rules_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "return $score > 0.5",
                "test_json": '{"score": "0.9"}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["rule_outcome"] == "True"

    def test_rules_test_cast_error_returns_error_status(self, rules_client, session):
        """An unparseable value for a configured type returns status='error'."""
        org = rules_client.org  # type: ignore[attr-defined]
        token = rules_client.token  # type: ignore[attr-defined]

        config = FieldTypeConfig(field_name="amount", configured_type="integer", o_id=org.o_id)
        session.add(config)
        session.commit()

        response = rules_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "return $amount > 100",
                "test_json": '{"amount": "not-a-number"}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "cast" in data["reason"].lower()

    def test_rules_test_no_config_passes_through(self, rules_client):
        """Fields with no config still work normally."""
        token = rules_client.token  # type: ignore[attr-defined]

        response = rules_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "return $amount > 100",
                "test_json": '{"amount": 150}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["rule_outcome"] == "True"
