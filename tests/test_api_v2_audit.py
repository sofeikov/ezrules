"""
Tests for FastAPI v2 audit trail endpoints.

These tests verify:
- Audit summary endpoint
- Rule history listing and filtering
- Config history listing and filtering
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Organisation,
    Role,
    Rule,
    RuleHistory,
    User,
)


@pytest.fixture(scope="function")
def audit_test_client(session):
    """
    Create a FastAPI test client with a user that has audit trail permission.
    """
    hashed_password = bcrypt.hashpw("auditadmin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with audit permission
    admin_role = session.query(Role).filter(Role.name == "audit_admin").first()
    if not admin_role:
        admin_role = Role(name="audit_admin", description="Can access audit trail")
        session.add(admin_role)
        session.commit()

    # Create admin user with role
    admin_user = session.query(User).filter(User.email == "auditadmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="auditadmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="auditadmin@example.com",
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.ACCESS_AUDIT_TRAIL)

    # Create a token for the user
    roles = [role.name for role in admin_user.roles]
    token = create_access_token(
        user_id=int(admin_user.id),
        email=str(admin_user.email),
        roles=roles,
    )

    client_data = {
        "user": admin_user,
        "role": admin_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_rule_with_history(session):
    """Create a rule with history entries for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create a rule
    rule = Rule(
        rid="audit_test_rule",
        logic="event.amount > 100",
        description="Test rule for audit",
        o_id=1,
        version=3,  # Current version is 3
    )
    session.add(rule)
    session.flush()

    # Create history entries (versions 1 and 2)
    history1 = RuleHistory(
        r_id=rule.r_id,
        rid="audit_test_rule",
        logic="event.amount > 50",
        description="Initial version",
        o_id=1,
        version=1,
    )
    history2 = RuleHistory(
        r_id=rule.r_id,
        rid="audit_test_rule",
        logic="event.amount > 75",
        description="Second version",
        o_id=1,
        version=2,
    )
    session.add(history1)
    session.add(history2)
    session.commit()

    return rule


# =============================================================================
# AUDIT SUMMARY TESTS
# =============================================================================


class TestAuditSummary:
    """Tests for GET /api/v2/audit."""

    def test_get_audit_summary(self, audit_test_client):
        """Should return audit summary."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_rule_versions" in data
        assert "total_config_versions" in data
        assert "rules_with_changes" in data
        assert "configs_with_changes" in data

    def test_audit_summary_unauthorized(self, audit_test_client):
        """Should return 401 without token."""
        response = audit_test_client.get("/api/v2/audit")
        assert response.status_code == 401


# =============================================================================
# RULE HISTORY LIST TESTS
# =============================================================================


class TestListRuleHistory:
    """Tests for GET /api/v2/audit/rules."""

    def test_list_rule_history(self, audit_test_client, sample_rule_with_history):
        """Should return paginated rule history."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit/rules",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] >= 2  # At least our test entries

    def test_list_rule_history_with_pagination(self, audit_test_client, sample_rule_with_history):
        """Should respect pagination parameters."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit/rules?limit=1&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 1
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_list_rule_history_filter_by_rule_id(self, audit_test_client, sample_rule_with_history):
        """Should filter by rule ID."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            f"/api/v2/audit/rules?rule_id={sample_rule_with_history.r_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2  # Exactly our 2 history entries
        for item in data["items"]:
            assert item["r_id"] == sample_rule_with_history.r_id


# =============================================================================
# RULE AUDIT DETAIL TESTS
# =============================================================================


class TestGetRuleAudit:
    """Tests for GET /api/v2/audit/rules/{rule_id}."""

    def test_get_rule_audit(self, audit_test_client, sample_rule_with_history):
        """Should return complete rule history."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            f"/api/v2/audit/rules/{sample_rule_with_history.r_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["r_id"] == sample_rule_with_history.r_id
        assert data["rid"] == "audit_test_rule"
        assert data["current_version"] == 3
        assert len(data["history"]) == 2

        # History should be ordered by version ascending
        assert data["history"][0]["version"] == 1
        assert data["history"][1]["version"] == 2

    def test_get_rule_audit_not_found(self, audit_test_client):
        """Should return 404 for non-existent rule."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit/rules/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# CONFIG HISTORY TESTS
# =============================================================================


class TestListConfigHistory:
    """Tests for GET /api/v2/audit/config."""

    def test_list_config_history(self, audit_test_client):
        """Should return paginated config history."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit/config",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_config_history_with_pagination(self, audit_test_client):
        """Should respect pagination parameters."""
        token = audit_test_client.test_data["token"]

        response = audit_test_client.get(
            "/api/v2/audit/config?limit=10&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestAuditPermissions:
    """Tests for permission checks on audit endpoints."""

    def test_audit_without_permission(self, session):
        """User without ACCESS_AUDIT_TRAIL permission should get 403."""
        hashed_password = bcrypt.hashpw("noauditpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_audit@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_audit@example.com",
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
                "/api/v2/audit",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_rule_history_without_permission(self, session):
        """User without ACCESS_AUDIT_TRAIL permission should get 403."""
        hashed_password = bcrypt.hashpw("noauditpass2".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_audit2@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_audit2@example.com",
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
                "/api/v2/audit/rules",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
