"""
Tests for FastAPI v2 users endpoints.

These tests verify:
- CRUD operations for users
- Role assignment and removal
- Permission checks
- Self-deletion/deactivation prevention
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, User


@pytest.fixture(scope="function")
def users_test_client(session):
    """
    Create a FastAPI test client with a user that has user management permissions.
    """
    hashed_password = bcrypt.hashpw("adminpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with user management permissions
    admin_role = session.query(Role).filter(Role.name == "user_admin").first()
    if not admin_role:
        admin_role = Role(name="user_admin", description="Can manage users")
        session.add(admin_role)
        session.commit()

    # Create admin user with role
    admin_user = session.query(User).filter(User.email == "useradmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="useradmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="useradmin@example.com",
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_USERS)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.CREATE_USER)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MODIFY_USER)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.DELETE_USER)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MANAGE_USER_ROLES)

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
def sample_user(session):
    """Create a sample user for testing."""
    hashed_password = bcrypt.hashpw("samplepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    user = User(
        email="sampleuser@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="sampleuser@example.com",
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture(scope="function")
def sample_role(session):
    """Create a sample role for testing."""
    role = session.query(Role).filter(Role.name == "test_role").first()
    if not role:
        role = Role(name="test_role", description="Test role for user tests")
        session.add(role)
        session.commit()
    return role


# =============================================================================
# LIST USERS TESTS
# =============================================================================


class TestListUsers:
    """Tests for GET /api/v2/users."""

    def test_list_users_success(self, users_test_client):
        """Should return list of users."""
        token = users_test_client.test_data["token"]

        response = users_test_client.get(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 1  # At least the admin user

    def test_list_users_includes_roles(self, users_test_client):
        """Should include roles in user data."""
        token = users_test_client.test_data["token"]

        response = users_test_client.get(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Find the admin user
        admin_user = next((u for u in data["users"] if u["email"] == "useradmin@example.com"), None)
        assert admin_user is not None
        assert "roles" in admin_user
        assert len(admin_user["roles"]) >= 1

    def test_list_users_unauthorized(self, users_test_client):
        """Should return 401 without token."""
        response = users_test_client.get("/api/v2/users")
        assert response.status_code == 401


# =============================================================================
# GET SINGLE USER TESTS
# =============================================================================


class TestGetUser:
    """Tests for GET /api/v2/users/{user_id}."""

    def test_get_user_success(self, users_test_client, sample_user):
        """Should return user details."""
        token = users_test_client.test_data["token"]

        response = users_test_client.get(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_user.id
        assert data["email"] == "sampleuser@example.com"
        assert data["active"] is True

    def test_get_user_not_found(self, users_test_client):
        """Should return 404 for non-existent user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.get(
            "/api/v2/users/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# CREATE USER TESTS
# =============================================================================


class TestCreateUser:
    """Tests for POST /api/v2/users."""

    def test_create_user_success(self, users_test_client):
        """Should create a new user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "newuser@example.com",
                "password": "newpassword123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["active"] is True

    def test_create_user_with_roles(self, users_test_client, sample_role):
        """Should create user with assigned roles."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "withroles@example.com",
                "password": "password123",
                "role_ids": [sample_role.id],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert len(data["user"]["roles"]) == 1
        assert data["user"]["roles"][0]["name"] == "test_role"

    def test_create_user_duplicate_email(self, users_test_client, sample_user):
        """Should return error for duplicate email."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "sampleuser@example.com",  # Duplicate
                "password": "password123",
            },
        )

        assert response.status_code == 201  # Returns 201 but success=False
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_user_invalid_email(self, users_test_client):
        """Should return 422 for invalid email."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "not-an-email",
                "password": "password123",
            },
        )

        assert response.status_code == 422

    def test_create_user_short_password(self, users_test_client):
        """Should return 422 for password too short."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "shortpass@example.com",
                "password": "12345",  # Too short
            },
        )

        assert response.status_code == 422

    def test_create_user_invalid_role_id(self, users_test_client):
        """Should return error for non-existent role ID."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "invalidrole@example.com",
                "password": "password123",
                "role_ids": [99999],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"]


# =============================================================================
# UPDATE USER TESTS
# =============================================================================


class TestUpdateUser:
    """Tests for PUT /api/v2/users/{user_id}."""

    def test_update_user_email(self, users_test_client, sample_user):
        """Should update user email."""
        token = users_test_client.test_data["token"]

        response = users_test_client.put(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "updated@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["email"] == "updated@example.com"

    def test_update_user_active_status(self, users_test_client, sample_user):
        """Should update user active status."""
        token = users_test_client.test_data["token"]

        response = users_test_client.put(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["active"] is False

    def test_update_user_password(self, users_test_client, sample_user):
        """Should update user password."""
        token = users_test_client.test_data["token"]

        response = users_test_client.put(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "newpassword123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_cannot_deactivate_self(self, users_test_client):
        """Should not allow deactivating yourself."""
        token = users_test_client.test_data["token"]
        admin_user = users_test_client.test_data["user"]

        response = users_test_client.put(
            f"/api/v2/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cannot deactivate yourself" in data["message"]

    def test_update_user_duplicate_email(self, users_test_client, sample_user):
        """Should return error for duplicate email."""
        token = users_test_client.test_data["token"]
        session = users_test_client.test_data["session"]

        # Create another user
        hashed_password = bcrypt.hashpw("otherpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        other_user = User(
            email="other@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="other@example.com",
        )
        session.add(other_user)
        session.commit()

        # Try to update sample_user to other_user's email
        response = users_test_client.put(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "other@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_update_nonexistent_user(self, users_test_client):
        """Should return 404 for non-existent user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.put(
            "/api/v2/users/99999",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "doesntmatter@example.com"},
        )

        assert response.status_code == 404


# =============================================================================
# DELETE USER TESTS
# =============================================================================


class TestDeleteUser:
    """Tests for DELETE /api/v2/users/{user_id}."""

    def test_delete_user_success(self, users_test_client, sample_user):
        """Should delete user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.delete(
            f"/api/v2/users/{sample_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_cannot_delete_self(self, users_test_client):
        """Should not allow deleting yourself."""
        token = users_test_client.test_data["token"]
        admin_user = users_test_client.test_data["user"]

        response = users_test_client.delete(
            f"/api/v2/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cannot delete yourself" in data["message"]

    def test_delete_nonexistent_user(self, users_test_client):
        """Should return 404 for non-existent user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.delete(
            "/api/v2/users/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# ROLE ASSIGNMENT TESTS
# =============================================================================


class TestRoleAssignment:
    """Tests for POST /api/v2/users/{user_id}/roles and DELETE /api/v2/users/{user_id}/roles/{role_id}."""

    def test_assign_role_success(self, users_test_client, sample_user, sample_role):
        """Should assign role to user."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            f"/api/v2/users/{sample_user.id}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": sample_role.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert any(r["name"] == "test_role" for r in data["user"]["roles"])

    def test_assign_role_already_assigned(self, users_test_client, sample_user, sample_role):
        """Should return error if role already assigned."""
        token = users_test_client.test_data["token"]
        session = users_test_client.test_data["session"]

        # Assign the role first
        sample_user.roles.append(sample_role)
        session.commit()

        # Try to assign again
        response = users_test_client.post(
            f"/api/v2/users/{sample_user.id}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": sample_role.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already assigned" in data["message"]

    def test_assign_nonexistent_role(self, users_test_client, sample_user):
        """Should return 404 for non-existent role."""
        token = users_test_client.test_data["token"]

        response = users_test_client.post(
            f"/api/v2/users/{sample_user.id}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": 99999},
        )

        assert response.status_code == 404

    def test_remove_role_success(self, users_test_client, sample_user, sample_role):
        """Should remove role from user."""
        token = users_test_client.test_data["token"]
        session = users_test_client.test_data["session"]

        # Assign the role first
        sample_user.roles.append(sample_role)
        session.commit()

        response = users_test_client.delete(
            f"/api/v2/users/{sample_user.id}/roles/{sample_role.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert all(r["name"] != "test_role" for r in data["user"]["roles"])

    def test_remove_role_not_assigned(self, users_test_client, sample_user, sample_role):
        """Should return error if role not assigned."""
        token = users_test_client.test_data["token"]

        response = users_test_client.delete(
            f"/api/v2/users/{sample_user.id}/roles/{sample_role.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not assigned" in data["message"]

    def test_remove_nonexistent_role(self, users_test_client, sample_user):
        """Should return 404 for non-existent role."""
        token = users_test_client.test_data["token"]

        response = users_test_client.delete(
            f"/api/v2/users/{sample_user.id}/roles/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestUserPermissions:
    """Tests for permission checks on user endpoints."""

    def test_list_users_without_permission(self, session):
        """User without VIEW_USERS permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_user@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_user@example.com",
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
                "/api/v2/users",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_create_user_without_permission(self, session):
        """User without CREATE_USER permission should get 403."""
        hashed_password = bcrypt.hashpw("nocreatepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="user_viewer", description="Can only view users")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_user@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_user@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_USERS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/users",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "email": "unauthorized@example.com",
                    "password": "password123",
                },
            )

            assert response.status_code == 403

    def test_delete_user_without_permission(self, session, sample_user):
        """User without DELETE_USER permission should get 403."""
        hashed_password = bcrypt.hashpw("nodeletepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="user_viewer_only", description="Can only view users")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly2_user@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly2_user@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_USERS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.delete(
                f"/api/v2/users/{sample_user.id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_manage_roles_without_permission(self, session, sample_user, sample_role):
        """User without MANAGE_USER_ROLES permission should get 403."""
        hashed_password = bcrypt.hashpw("norolespass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="user_viewer_noroles", description="Can only view users")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_noroles@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_noroles@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_USERS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                f"/api/v2/users/{sample_user.id}/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_id": sample_role.id},
            )

            assert response.status_code == 403
