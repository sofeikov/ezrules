"""
Tests for FastAPI v2 roles endpoints.

These tests verify:
- CRUD operations for roles
- Permission management for roles
- Protection of system roles
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, Organisation, Role, RoleActions, User


@pytest.fixture(scope="function")
def roles_test_client(session):
    """
    Create a FastAPI test client with a user that has role management permissions.
    """
    hashed_password = bcrypt.hashpw("roleadmin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with role management permissions
    admin_role = session.query(Role).filter(Role.name == "role_admin").first()
    if not admin_role:
        admin_role = Role(name="role_admin", description="Can manage roles")
        session.add(admin_role)
        session.commit()

    # Create admin user with role
    admin_user = session.query(User).filter(User.email == "roleadmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="roleadmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="roleadmin@example.com",
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_ROLES)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.CREATE_ROLE)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MODIFY_ROLE)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.DELETE_ROLE)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MANAGE_PERMISSIONS)

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
def sample_role(session):
    """Create a sample role for testing."""
    role = session.query(Role).filter(Role.name == "sample_test_role").first()
    if not role:
        role = Role(name="sample_test_role", description="Sample role for testing")
        session.add(role)
        session.commit()
    return role


@pytest.fixture(scope="function")
def protected_role(session):
    """Create an admin role (protected)."""
    role = session.query(Role).filter(Role.name == "admin").first()
    if not role:
        role = Role(name="admin", description="Admin role")
        session.add(role)
        session.commit()
    return role


# =============================================================================
# LIST PERMISSIONS TESTS
# =============================================================================


class TestListPermissions:
    """Tests for GET /api/v2/roles/permissions."""

    def test_list_permissions_success(self, roles_test_client):
        """Should return list of all permissions."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            "/api/v2/roles/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "permissions" in data
        assert isinstance(data["permissions"], list)
        assert len(data["permissions"]) > 0

        # Check structure
        perm = data["permissions"][0]
        assert "id" in perm
        assert "name" in perm
        assert "resource_type" in perm

    def test_list_permissions_unauthorized(self, roles_test_client):
        """Should return 401 without token."""
        response = roles_test_client.get("/api/v2/roles/permissions")
        assert response.status_code == 401


# =============================================================================
# LIST ROLES TESTS
# =============================================================================


class TestListRoles:
    """Tests for GET /api/v2/roles."""

    def test_list_roles_success(self, roles_test_client):
        """Should return list of roles."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert isinstance(data["roles"], list)
        assert len(data["roles"]) >= 1

    def test_list_roles_includes_user_count(self, roles_test_client):
        """Should include user_count in role data."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Find the role_admin role (has at least one user)
        admin_role = next((r for r in data["roles"] if r["name"] == "role_admin"), None)
        assert admin_role is not None
        assert "user_count" in admin_role
        assert admin_role["user_count"] >= 1

    def test_list_roles_unauthorized(self, roles_test_client):
        """Should return 401 without token."""
        response = roles_test_client.get("/api/v2/roles")
        assert response.status_code == 401


# =============================================================================
# GET SINGLE ROLE TESTS
# =============================================================================


class TestGetRole:
    """Tests for GET /api/v2/roles/{role_id}."""

    def test_get_role_success(self, roles_test_client, sample_role):
        """Should return role details."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            f"/api/v2/roles/{sample_role.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_role.id
        assert data["name"] == "sample_test_role"
        assert "permissions" in data

    def test_get_role_not_found(self, roles_test_client):
        """Should return 404 for non-existent role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            "/api/v2/roles/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# CREATE ROLE TESTS
# =============================================================================


class TestCreateRole:
    """Tests for POST /api/v2/roles."""

    def test_create_role_success(self, roles_test_client):
        """Should create a new role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.post(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "new_custom_role",
                "description": "A new custom role",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["role"]["name"] == "new_custom_role"
        assert data["role"]["description"] == "A new custom role"

    def test_create_role_minimal(self, roles_test_client):
        """Should create role with just name."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.post(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "minimal_role"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["role"]["name"] == "minimal_role"

    def test_create_role_duplicate_name(self, roles_test_client, sample_role):
        """Should return error for duplicate name."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.post(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "sample_test_role"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_role_empty_name(self, roles_test_client):
        """Should return 422 for empty name."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.post(
            "/api/v2/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": ""},
        )

        assert response.status_code == 422


# =============================================================================
# UPDATE ROLE TESTS
# =============================================================================


class TestUpdateRole:
    """Tests for PUT /api/v2/roles/{role_id}."""

    def test_update_role_name(self, roles_test_client, sample_role):
        """Should update role name."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            f"/api/v2/roles/{sample_role.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "updated_role_name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["role"]["name"] == "updated_role_name"

    def test_update_role_description(self, roles_test_client, sample_role):
        """Should update role description."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            f"/api/v2/roles/{sample_role.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "Updated description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["role"]["description"] == "Updated description"

    def test_cannot_rename_protected_role(self, roles_test_client, protected_role):
        """Should not allow renaming protected roles."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            f"/api/v2/roles/{protected_role.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "renamed_admin"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "protected" in data["error"].lower()

    def test_update_protected_role_description(self, roles_test_client, protected_role):
        """Should allow updating description of protected role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            f"/api/v2/roles/{protected_role.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "Updated admin description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["role"]["description"] == "Updated admin description"

    def test_update_nonexistent_role(self, roles_test_client):
        """Should return 404 for non-existent role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            "/api/v2/roles/99999",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "doesntmatter"},
        )

        assert response.status_code == 404


# =============================================================================
# DELETE ROLE TESTS
# =============================================================================


class TestDeleteRole:
    """Tests for DELETE /api/v2/roles/{role_id}."""

    def test_delete_role_success(self, roles_test_client, session):
        """Should delete role without users."""
        token = roles_test_client.test_data["token"]

        # Create a role to delete
        role_to_delete = Role(name="role_to_delete", description="Will be deleted")
        session.add(role_to_delete)
        session.commit()

        response = roles_test_client.delete(
            f"/api/v2/roles/{role_to_delete.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_cannot_delete_protected_role(self, roles_test_client, protected_role):
        """Should not allow deleting protected roles."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.delete(
            f"/api/v2/roles/{protected_role.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "protected" in data["error"].lower()

    def test_cannot_delete_role_with_users(self, roles_test_client):
        """Should not allow deleting role with assigned users."""
        token = roles_test_client.test_data["token"]
        admin_role = roles_test_client.test_data["role"]

        response = roles_test_client.delete(
            f"/api/v2/roles/{admin_role.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "assigned user" in data["error"].lower()

    def test_delete_nonexistent_role(self, roles_test_client):
        """Should return 404 for non-existent role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.delete(
            "/api/v2/roles/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# ROLE PERMISSIONS TESTS
# =============================================================================


class TestRolePermissions:
    """Tests for GET/PUT /api/v2/roles/{role_id}/permissions."""

    def test_get_role_permissions(self, roles_test_client, sample_role):
        """Should get permissions for a role."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.get(
            f"/api/v2/roles/{sample_role.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "role" in data
        assert "permissions" in data["role"]

    def test_update_role_permissions(self, roles_test_client, sample_role, session):
        """Should update permissions for a role."""
        token = roles_test_client.test_data["token"]

        # Get some action IDs to assign
        actions = session.query(Action).limit(3).all()
        action_ids = [a.id for a in actions]

        response = roles_test_client.put(
            f"/api/v2/roles/{sample_role.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission_ids": action_ids},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["role"]["permissions"]) == 3

    def test_update_role_permissions_empty_list(self, roles_test_client, sample_role, session):
        """Should allow setting empty permissions (remove all)."""
        token = roles_test_client.test_data["token"]

        # First add some permissions
        actions = session.query(Action).limit(2).all()
        for action in actions:
            ra = RoleActions(role_id=sample_role.id, action_id=action.id)
            session.add(ra)
        session.commit()

        # Now remove all
        response = roles_test_client.put(
            f"/api/v2/roles/{sample_role.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission_ids": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["role"]["permissions"]) == 0

    def test_update_role_permissions_invalid_id(self, roles_test_client, sample_role):
        """Should return error for invalid permission ID."""
        token = roles_test_client.test_data["token"]

        response = roles_test_client.put(
            f"/api/v2/roles/{sample_role.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission_ids": [99999]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"]


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestRolePermissionChecks:
    """Tests for permission checks on role endpoints."""

    def test_list_roles_without_permission(self, session):
        """User without VIEW_ROLES permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_role@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_role@example.com",
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
                "/api/v2/roles",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_create_role_without_permission(self, session):
        """User without CREATE_ROLE permission should get 403."""
        hashed_password = bcrypt.hashpw("nocreatepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="role_viewer", description="Can only view roles")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_role@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_role@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_ROLES)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "unauthorized_role"},
            )

            assert response.status_code == 403

    def test_manage_permissions_without_permission(self, session, sample_role):
        """User without MANAGE_PERMISSIONS permission should get 403."""
        hashed_password = bcrypt.hashpw("nomanagepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="role_viewer_only", description="Can only view roles")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly2_role@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly2_role@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_ROLES)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.put(
                f"/api/v2/roles/{sample_role.id}/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission_ids": [1]},
            )

            assert response.status_code == 403
