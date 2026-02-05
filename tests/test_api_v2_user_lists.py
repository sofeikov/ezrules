"""
Tests for FastAPI v2 user lists endpoints.

These tests verify:
- CRUD operations for user lists
- Entry management (add, bulk add, delete)
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, User, UserList, UserListEntry


@pytest.fixture(scope="function")
def user_lists_test_client(session):
    """
    Create a FastAPI test client with a user that has list management permissions.
    """
    hashed_password = bcrypt.hashpw("listadmin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with list management permissions
    admin_role = session.query(Role).filter(Role.name == "list_admin").first()
    if not admin_role:
        admin_role = Role(name="list_admin", description="Can manage lists")
        session.add(admin_role)
        session.commit()

    # Create admin user with role
    admin_user = session.query(User).filter(User.email == "listadmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="listadmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="listadmin@example.com",
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_LISTS)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.CREATE_LIST)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MODIFY_LIST)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.DELETE_LIST)

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
def sample_user_list(session):
    """Create a sample user list for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    user_list = UserList(list_name="TestCountries", o_id=1)
    session.add(user_list)
    session.commit()
    return user_list


@pytest.fixture(scope="function")
def sample_user_list_with_entries(session):
    """Create a sample user list with entries for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    user_list = UserList(list_name="CountriesWithEntries", o_id=1)
    session.add(user_list)
    session.flush()

    entries = ["US", "CA", "MX"]
    for value in entries:
        entry = UserListEntry(entry_value=value, ul_id=user_list.ul_id)
        session.add(entry)

    session.commit()
    return user_list


# =============================================================================
# LIST USER LISTS TESTS
# =============================================================================


class TestListUserLists:
    """Tests for GET /api/v2/user-lists."""

    def test_list_user_lists_success(self, user_lists_test_client, sample_user_list):
        """Should return list of user lists."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.get(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "lists" in data
        assert isinstance(data["lists"], list)
        assert len(data["lists"]) >= 1

    def test_list_user_lists_includes_entry_count(self, user_lists_test_client, sample_user_list_with_entries):
        """Should include entry_count in list data."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.get(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Find our test list
        test_list = next((l for l in data["lists"] if l["name"] == "CountriesWithEntries"), None)
        assert test_list is not None
        assert test_list["entry_count"] == 3

    def test_list_user_lists_unauthorized(self, user_lists_test_client):
        """Should return 401 without token."""
        response = user_lists_test_client.get("/api/v2/user-lists")
        assert response.status_code == 401


# =============================================================================
# GET SINGLE USER LIST TESTS
# =============================================================================


class TestGetUserList:
    """Tests for GET /api/v2/user-lists/{list_id}."""

    def test_get_user_list_success(self, user_lists_test_client, sample_user_list_with_entries):
        """Should return list with entries."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.get(
            f"/api/v2/user-lists/{sample_user_list_with_entries.ul_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "CountriesWithEntries"
        assert "entries" in data
        assert len(data["entries"]) == 3

    def test_get_user_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.get(
            "/api/v2/user-lists/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# CREATE USER LIST TESTS
# =============================================================================


class TestCreateUserList:
    """Tests for POST /api/v2/user-lists."""

    def test_create_user_list_success(self, user_lists_test_client):
        """Should create a new user list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "HighRiskCountries"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["list"]["name"] == "HighRiskCountries"
        assert data["list"]["entry_count"] == 0

    def test_create_user_list_duplicate_name(self, user_lists_test_client, sample_user_list):
        """Should return error for duplicate name."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "TestCountries"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_user_list_empty_name(self, user_lists_test_client):
        """Should return 422 for empty name."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": ""},
        )

        assert response.status_code == 422


# =============================================================================
# UPDATE USER LIST TESTS
# =============================================================================


class TestUpdateUserList:
    """Tests for PUT /api/v2/user-lists/{list_id}."""

    def test_update_user_list_name(self, user_lists_test_client, sample_user_list):
        """Should update list name."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.put(
            f"/api/v2/user-lists/{sample_user_list.ul_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "RenamedList"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["list"]["name"] == "RenamedList"

    def test_update_user_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.put(
            "/api/v2/user-lists/99999",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "DoesntMatter"},
        )

        assert response.status_code == 404


# =============================================================================
# DELETE USER LIST TESTS
# =============================================================================


class TestDeleteUserList:
    """Tests for DELETE /api/v2/user-lists/{list_id}."""

    def test_delete_user_list_success(self, user_lists_test_client, sample_user_list):
        """Should delete list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.delete(
            f"/api/v2/user-lists/{sample_user_list.ul_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_delete_user_list_with_entries(self, user_lists_test_client, sample_user_list_with_entries):
        """Should delete list and all its entries (cascade)."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.delete(
            f"/api/v2/user-lists/{sample_user_list_with_entries.ul_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_delete_user_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.delete(
            "/api/v2/user-lists/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# ADD ENTRY TESTS
# =============================================================================


class TestAddEntry:
    """Tests for POST /api/v2/user-lists/{list_id}/entries."""

    def test_add_entry_success(self, user_lists_test_client, sample_user_list):
        """Should add entry to list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            f"/api/v2/user-lists/{sample_user_list.ul_id}/entries",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "US"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["entry"]["value"] == "US"

    def test_add_entry_duplicate(self, user_lists_test_client, sample_user_list_with_entries):
        """Should return error for duplicate entry."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            f"/api/v2/user-lists/{sample_user_list_with_entries.ul_id}/entries",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "US"},  # Already exists
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_add_entry_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            "/api/v2/user-lists/99999/entries",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "US"},
        )

        assert response.status_code == 404


# =============================================================================
# BULK ADD ENTRIES TESTS
# =============================================================================


class TestBulkAddEntries:
    """Tests for POST /api/v2/user-lists/{list_id}/entries/bulk."""

    def test_bulk_add_entries_success(self, user_lists_test_client, sample_user_list):
        """Should bulk add entries."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            f"/api/v2/user-lists/{sample_user_list.ul_id}/entries/bulk",
            headers={"Authorization": f"Bearer {token}"},
            json={"values": ["US", "CA", "MX", "BR"]},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert len(data["added"]) == 4
        assert len(data["skipped"]) == 0

    def test_bulk_add_entries_with_duplicates(self, user_lists_test_client, sample_user_list_with_entries):
        """Should skip existing entries."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            f"/api/v2/user-lists/{sample_user_list_with_entries.ul_id}/entries/bulk",
            headers={"Authorization": f"Bearer {token}"},
            json={"values": ["US", "CA", "BR", "AR"]},  # US, CA already exist
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert len(data["added"]) == 2  # BR, AR
        assert len(data["skipped"]) == 2  # US, CA

    def test_bulk_add_entries_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.post(
            "/api/v2/user-lists/99999/entries/bulk",
            headers={"Authorization": f"Bearer {token}"},
            json={"values": ["US"]},
        )

        assert response.status_code == 404


# =============================================================================
# DELETE ENTRY TESTS
# =============================================================================


class TestDeleteEntry:
    """Tests for DELETE /api/v2/user-lists/{list_id}/entries/{entry_id}."""

    def test_delete_entry_success(self, user_lists_test_client, sample_user_list_with_entries, session):
        """Should delete entry."""
        token = user_lists_test_client.test_data["token"]

        # Get an entry ID
        entry = session.query(UserListEntry).filter(UserListEntry.ul_id == sample_user_list_with_entries.ul_id).first()

        response = user_lists_test_client.delete(
            f"/api/v2/user-lists/{sample_user_list_with_entries.ul_id}/entries/{entry.ule_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_delete_entry_not_found(self, user_lists_test_client, sample_user_list):
        """Should return 404 for non-existent entry."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.delete(
            f"/api/v2/user-lists/{sample_user_list.ul_id}/entries/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_delete_entry_list_not_found(self, user_lists_test_client):
        """Should return 404 for non-existent list."""
        token = user_lists_test_client.test_data["token"]

        response = user_lists_test_client.delete(
            "/api/v2/user-lists/99999/entries/1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestUserListPermissions:
    """Tests for permission checks on user list endpoints."""

    def test_view_lists_without_permission(self, session):
        """User without VIEW_LISTS permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_list@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_list@example.com",
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
                "/api/v2/user-lists",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_create_list_without_permission(self, session):
        """User without CREATE_LIST permission should get 403."""
        hashed_password = bcrypt.hashpw("nocreatepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="list_viewer", description="Can only view lists")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_list@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_list@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_LISTS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/user-lists",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "UnauthorizedList"},
            )

            assert response.status_code == 403

    def test_modify_list_without_permission(self, session, sample_user_list):
        """User without MODIFY_LIST permission should get 403."""
        hashed_password = bcrypt.hashpw("nomodifypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="list_viewer_only", description="Can only view lists")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly2_list@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly2_list@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_LISTS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                f"/api/v2/user-lists/{sample_user_list.ul_id}/entries",
                headers={"Authorization": f"Bearer {token}"},
                json={"value": "TEST"},
            )

            assert response.status_code == 403
