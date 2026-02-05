"""
Tests for FastAPI v2 rules endpoints.

These tests verify:
- CRUD operations for rules
- Rule validation and verification
- Rule history and revisions
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, User
from ezrules.models.backend_core import Rule as RuleModel


@pytest.fixture(scope="function")
def rules_test_client(session):
    """
    Create a FastAPI test client with a user that has rule permissions.
    """
    hashed_password = bcrypt.hashpw("rulepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with rule permissions
    rule_role = session.query(Role).filter(Role.name == "rule_manager").first()
    if not rule_role:
        rule_role = Role(name="rule_manager", description="Can manage rules")
        session.add(rule_role)
        session.commit()

    # Create user with role
    rule_user = session.query(User).filter(User.email == "ruleuser@example.com").first()
    if not rule_user:
        rule_user = User(
            email="ruleuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="ruleuser@example.com",
        )
        rule_user.roles.append(rule_role)
        session.add(rule_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(rule_role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(rule_role.id, PermissionAction.CREATE_RULE)
    PermissionManager.grant_permission(rule_role.id, PermissionAction.MODIFY_RULE)

    # Create a token for the user
    roles = [role.name for role in rule_user.roles]
    token = create_access_token(
        user_id=int(rule_user.id),
        email=str(rule_user.email),
        roles=roles,
    )

    client_data = {
        "user": rule_user,
        "role": rule_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_rule(session):
    """Create a sample rule for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    rule = RuleModel(
        rid="test_rule_001",
        logic="event.amount > 100",
        description="Test rule for amounts over 100",
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()
    return rule


# =============================================================================
# LIST RULES TESTS
# =============================================================================


class TestListRules:
    """Tests for GET /api/v2/rules."""

    def test_list_rules_empty(self, rules_test_client):
        """Should return empty list when no rules exist."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert isinstance(data["rules"], list)

    def test_list_rules_with_rules(self, rules_test_client, sample_rule):
        """Should return list of rules."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rules"]) >= 1

        # Find our test rule
        test_rule = next((r for r in data["rules"] if r["rid"] == "test_rule_001"), None)
        assert test_rule is not None
        assert test_rule["description"] == "Test rule for amounts over 100"

    def test_list_rules_includes_evaluator_endpoint(self, rules_test_client):
        """Should include evaluator endpoint in response."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "evaluator_endpoint" in data

    def test_list_rules_unauthorized(self, rules_test_client):
        """Should return 401 without token."""
        response = rules_test_client.get("/api/v2/rules")
        assert response.status_code == 401


# =============================================================================
# GET SINGLE RULE TESTS
# =============================================================================


class TestGetRule:
    """Tests for GET /api/v2/rules/{id}."""

    def test_get_rule_success(self, rules_test_client, sample_rule):
        """Should return rule details."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            f"/api/v2/rules/{sample_rule.r_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["r_id"] == sample_rule.r_id
        assert data["rid"] == "test_rule_001"
        assert data["logic"] == "event.amount > 100"
        assert "revisions" in data

    def test_get_rule_not_found(self, rules_test_client):
        """Should return 404 for non-existent rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            "/api/v2/rules/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# CREATE RULE TESTS
# =============================================================================


class TestCreateRule:
    """Tests for POST /api/v2/rules."""

    def test_create_rule_success(self, rules_test_client):
        """Should create a new rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "new_rule_001",
                "description": "A new test rule",
                "logic": "event.value > 50",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["rule"]["rid"] == "new_rule_001"
        assert data["rule"]["logic"] == "event.value > 50"

    def test_create_rule_invalid_logic(self, rules_test_client):
        """Should return error for invalid rule logic."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "bad_rule",
                "description": "A rule with invalid syntax",
                "logic": "this is not valid python {{{",
            },
        )

        assert response.status_code == 201  # Returns 201 but success=False
        data = response.json()
        assert data["success"] is False
        assert "error" in data

    def test_create_rule_missing_fields(self, rules_test_client):
        """Should return 422 for missing required fields."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={"rid": "incomplete_rule"},  # Missing description and logic
        )

        assert response.status_code == 422


# =============================================================================
# UPDATE RULE TESTS
# =============================================================================


class TestUpdateRule:
    """Tests for PUT /api/v2/rules/{id}."""

    def test_update_rule_success(self, rules_test_client, sample_rule):
        """Should update existing rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.put(
            f"/api/v2/rules/{sample_rule.r_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "description": "Updated description",
                "logic": "event.amount > 200",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["rule"]["description"] == "Updated description"
        assert data["rule"]["logic"] == "event.amount > 200"

    def test_update_rule_partial(self, rules_test_client, sample_rule):
        """Should allow partial updates."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.put(
            f"/api/v2/rules/{sample_rule.r_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "Only updating description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["rule"]["description"] == "Only updating description"
        assert data["rule"]["logic"] == "event.amount > 100"  # Unchanged

    def test_update_rule_not_found(self, rules_test_client):
        """Should return 404 for non-existent rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.put(
            "/api/v2/rules/99999",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "Won't work"},
        )

        assert response.status_code == 404

    def test_update_rule_invalid_logic(self, rules_test_client, sample_rule):
        """Should return error for invalid rule logic."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.put(
            f"/api/v2/rules/{sample_rule.r_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logic": "invalid syntax {{{"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data


# =============================================================================
# VERIFY RULE TESTS
# =============================================================================


class TestVerifyRule:
    """Tests for POST /api/v2/rules/verify."""

    def test_verify_rule_valid(self, rules_test_client):
        """Should return parameters for valid rule."""
        token = rules_test_client.test_data["token"]

        # The Rule class uses $variable notation for param extraction
        response = rules_test_client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": "$amount > 100 and $currency == 'USD'"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "params" in data
        assert "amount" in data["params"]
        assert "currency" in data["params"]

    def test_verify_rule_invalid(self, rules_test_client):
        """Should return empty params for invalid rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": "invalid {{{ syntax"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["params"] == []


# =============================================================================
# TEST RULE TESTS
# =============================================================================


class TestTestRule:
    """Tests for POST /api/v2/rules/test."""

    def test_test_rule_success_true(self, rules_test_client):
        """Should return True for matching rule."""
        token = rules_test_client.test_data["token"]

        # Rules use $variable notation and need a return statement
        response = rules_test_client.post(
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
        assert data["rule_outcome"] is True

    def test_test_rule_success_false(self, rules_test_client):
        """Should return False for non-matching rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "return $amount > 100",
                "test_json": '{"amount": 50}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["rule_outcome"] is False

    def test_test_rule_invalid_json(self, rules_test_client):
        """Should return error for malformed test JSON."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "event.amount > 100",
                "test_json": "not valid json {{{",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "malformed" in data["reason"].lower()

    def test_test_rule_invalid_rule(self, rules_test_client):
        """Should return error for invalid rule syntax."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "invalid {{{ syntax",
                "test_json": '{"event": {"amount": 100}}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "invalid" in data["reason"].lower()


# =============================================================================
# RULE HISTORY TESTS
# =============================================================================


class TestRuleHistory:
    """Tests for GET /api/v2/rules/{id}/history."""

    def test_get_history_success(self, rules_test_client, sample_rule):
        """Should return rule history."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            f"/api/v2/rules/{sample_rule.r_id}/history",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["r_id"] == sample_rule.r_id
        assert "history" in data
        assert isinstance(data["history"], list)
        # Should have at least the current version
        assert len(data["history"]) >= 1
        # Last entry should be marked as current
        assert data["history"][-1]["is_current"] is True

    def test_get_history_with_limit(self, rules_test_client, sample_rule):
        """Should respect limit parameter."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            f"/api/v2/rules/{sample_rule.r_id}/history?limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    def test_get_history_not_found(self, rules_test_client):
        """Should return 404 for non-existent rule."""
        token = rules_test_client.test_data["token"]

        response = rules_test_client.get(
            "/api/v2/rules/99999/history",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestRulePermissions:
    """Tests for permission checks on rule endpoints."""

    def test_view_rules_without_permission(self, session):
        """User without VIEW_RULES permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm@example.com",
        )
        session.add(no_perm_user)
        session.commit()

        # Initialize permissions (but don't grant any to this user)
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        token = create_access_token(
            user_id=int(no_perm_user.id),
            email=str(no_perm_user.email),
            roles=[],
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v2/rules",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
