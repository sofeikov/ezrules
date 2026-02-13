"""
Tests for FastAPI v2 outcomes endpoints.

These tests verify:
- CRUD operations for allowed outcomes
- Duplicate outcome handling
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AllowedOutcome, Organisation, Role, User


@pytest.fixture(scope="function")
def outcomes_test_client(session):
    """
    Create a FastAPI test client with a user that has outcome permissions.
    """
    hashed_password = bcrypt.hashpw("outcomepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with outcome permissions
    outcome_role = session.query(Role).filter(Role.name == "outcome_manager").first()
    if not outcome_role:
        outcome_role = Role(name="outcome_manager", description="Can manage outcomes")
        session.add(outcome_role)
        session.commit()

    # Create user with role
    outcome_user = session.query(User).filter(User.email == "outcomeuser@example.com").first()
    if not outcome_user:
        outcome_user = User(
            email="outcomeuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="outcomeuser@example.com",
        )
        outcome_user.roles.append(outcome_role)
        session.add(outcome_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(outcome_role.id, PermissionAction.VIEW_OUTCOMES)
    PermissionManager.grant_permission(outcome_role.id, PermissionAction.CREATE_OUTCOME)
    PermissionManager.grant_permission(outcome_role.id, PermissionAction.DELETE_OUTCOME)

    # Create a token for the user
    roles = [role.name for role in outcome_user.roles]
    token = create_access_token(
        user_id=int(outcome_user.id),
        email=str(outcome_user.email),
        roles=roles,
    )

    client_data = {
        "user": outcome_user,
        "role": outcome_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_outcome(session):
    """Create a sample outcome for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    outcome = AllowedOutcome(
        outcome_name="TEST_OUTCOME",
        o_id=org.o_id,
    )
    session.add(outcome)
    session.commit()
    return outcome


# =============================================================================
# LIST OUTCOMES TESTS
# =============================================================================


class TestListOutcomes:
    """Tests for GET /api/v2/outcomes."""

    def test_list_outcomes_empty(self, outcomes_test_client):
        """Should return empty list when no outcomes exist."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.get(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "outcomes" in data
        assert isinstance(data["outcomes"], list)

    def test_list_outcomes_with_outcomes(self, outcomes_test_client, sample_outcome):
        """Should return list of outcomes."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.get(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["outcomes"]) >= 1

        # Find our test outcome
        test_outcome = next((o for o in data["outcomes"] if o["outcome_name"] == "TEST_OUTCOME"), None)
        assert test_outcome is not None

    def test_list_outcomes_unauthorized(self, outcomes_test_client):
        """Should return 401 without token."""
        response = outcomes_test_client.get("/api/v2/outcomes")
        assert response.status_code == 401


# =============================================================================
# CREATE OUTCOME TESTS
# =============================================================================


class TestCreateOutcome:
    """Tests for POST /api/v2/outcomes."""

    def test_create_outcome_success(self, outcomes_test_client):
        """Should create a new outcome."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.post(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome_name": "new_outcome"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["outcome"]["outcome_name"] == "NEW_OUTCOME"  # Should be uppercase

    def test_create_outcome_uppercase_conversion(self, outcomes_test_client):
        """Should convert outcome name to uppercase."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.post(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome_name": "MixedCase"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["outcome"]["outcome_name"] == "MIXEDCASE"

    def test_create_duplicate_outcome(self, outcomes_test_client, sample_outcome):
        """Should return error for duplicate outcome."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.post(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome_name": "TEST_OUTCOME"},
        )

        assert response.status_code == 201  # Returns 201 but success=False
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_outcome_missing_name(self, outcomes_test_client):
        """Should return 422 for missing outcome_name."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.post(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        assert response.status_code == 422

    def test_create_outcome_empty_name(self, outcomes_test_client):
        """Should return 422 for empty outcome_name."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.post(
            "/api/v2/outcomes",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome_name": ""},
        )

        assert response.status_code == 422


# =============================================================================
# DELETE OUTCOME TESTS
# =============================================================================


class TestDeleteOutcome:
    """Tests for DELETE /api/v2/outcomes/{outcome_name}."""

    def test_delete_outcome_success(self, outcomes_test_client, sample_outcome):
        """Should delete existing outcome."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.delete(
            "/api/v2/outcomes/TEST_OUTCOME",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_delete_outcome_case_insensitive(self, outcomes_test_client, sample_outcome):
        """Should delete outcome regardless of case."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.delete(
            "/api/v2/outcomes/test_outcome",  # lowercase
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_delete_nonexistent_outcome(self, outcomes_test_client):
        """Should return 404 for non-existent outcome."""
        token = outcomes_test_client.test_data["token"]

        response = outcomes_test_client.delete(
            "/api/v2/outcomes/DOES_NOT_EXIST",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestOutcomePermissions:
    """Tests for permission checks on outcome endpoints."""

    def test_view_outcomes_without_permission(self, session):
        """User without VIEW_OUTCOMES permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_outcome@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_outcome@example.com",
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
                "/api/v2/outcomes",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_create_outcome_without_permission(self, session):
        """User without CREATE_OUTCOME permission should get 403."""
        hashed_password = bcrypt.hashpw("nocreatepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="outcome_viewer", description="Can only view outcomes")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_outcome@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_outcome@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_OUTCOMES)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/outcomes",
                headers={"Authorization": f"Bearer {token}"},
                json={"outcome_name": "UNAUTHORIZED"},
            )

            assert response.status_code == 403

    def test_delete_outcome_without_permission(self, session, sample_outcome):
        """User without DELETE_OUTCOME permission should get 403."""
        hashed_password = bcrypt.hashpw("nodeletepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="outcome_viewer_only", description="Can only view outcomes")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly2_outcome@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly2_outcome@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_OUTCOMES)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.delete(
                f"/api/v2/outcomes/{sample_outcome.outcome_name}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
