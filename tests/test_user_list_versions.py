"""Tests for org-scoped user-list version records."""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules import cli as cli_module
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.demo_data import seed_demo_user_lists
from ezrules.models.backend_core import Role, User, UserList, UserListEntry, UserListHistory, UserListVersion


@pytest.fixture(scope="function")
def user_list_version_client(session):
    """Create a FastAPI test client with list-management permissions."""
    hashed_password = bcrypt.hashpw("versionadmin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    admin_role = Role(name="version_list_admin", description="Can manage versioned lists", o_id=1)
    session.add(admin_role)
    session.commit()

    admin_user = User(
        email="version-list-admin@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="version-list-admin@example.com",
        o_id=1,
    )
    admin_user.roles.append(admin_role)
    session.add(admin_user)
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_LISTS)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.CREATE_LIST)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MODIFY_LIST)
    PermissionManager.grant_permission(admin_role.id, PermissionAction.DELETE_LIST)

    token = create_access_token(
        user_id=int(admin_user.id),
        email=str(admin_user.email),
        roles=[str(admin_role.name)],
        org_id=int(admin_user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token}  # type: ignore[attr-defined]
        yield client


def _auth_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.test_data['token']}"}


def _version(session, org_id: int = 1) -> int | None:
    session.expire_all()
    version = session.get(UserListVersion, org_id)
    return None if version is None else int(version.version)


def _create_user_list(session, *, name: str = "VersionedCountries", org_id: int = 1) -> UserList:
    user_list = UserList(list_name=name, o_id=org_id)
    session.add(user_list)
    session.commit()
    return user_list


def _create_entry(session, user_list: UserList, value: str) -> UserListEntry:
    entry = UserListEntry(entry_value=value, ul_id=int(user_list.ul_id))
    session.add(entry)
    session.commit()
    return entry


def test_bootstrap_organisation_creates_user_list_version_row(session):
    organisation, created = cli_module._bootstrap_organisation(session, org_name="versioned-org")

    assert created is True
    version = session.get(UserListVersion, int(organisation.o_id))
    assert version is not None
    assert int(version.version) == 1


def test_api_list_create_rename_delete_increment_version(user_list_version_client, session):
    headers = _auth_headers(user_list_version_client)

    create_response = user_list_version_client.post(
        "/api/v2/user-lists",
        headers=headers,
        json={"name": "LifecycleCountries"},
    )
    assert create_response.status_code == 201
    assert create_response.json()["success"] is True
    assert _version(session) == 1

    list_id = create_response.json()["list"]["id"]
    rename_response = user_list_version_client.put(
        f"/api/v2/user-lists/{list_id}",
        headers=headers,
        json={"name": "RenamedLifecycleCountries"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["success"] is True
    assert _version(session) == 2

    delete_response = user_list_version_client.delete(f"/api/v2/user-lists/{list_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True
    assert _version(session) == 3
    assert session.query(UserListHistory).filter(UserListHistory.o_id == 1).count() == 3


def test_api_entry_mutations_increment_only_when_entries_change(user_list_version_client, session):
    headers = _auth_headers(user_list_version_client)
    create_response = user_list_version_client.post(
        "/api/v2/user-lists",
        headers=headers,
        json={"name": "EntryCountries"},
    )
    list_id = create_response.json()["list"]["id"]
    assert _version(session) == 1

    add_response = user_list_version_client.post(
        f"/api/v2/user-lists/{list_id}/entries",
        headers=headers,
        json={"value": "US"},
    )
    assert add_response.status_code == 201
    assert add_response.json()["success"] is True
    assert _version(session) == 2

    duplicate_response = user_list_version_client.post(
        f"/api/v2/user-lists/{list_id}/entries",
        headers=headers,
        json={"value": "US"},
    )
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["success"] is False
    assert _version(session) == 2

    bulk_response = user_list_version_client.post(
        f"/api/v2/user-lists/{list_id}/entries/bulk",
        headers=headers,
        json={"values": ["US", "CA", "MX"]},
    )
    assert bulk_response.status_code == 201
    assert bulk_response.json()["added"] == ["CA", "MX"]
    assert bulk_response.json()["skipped"] == ["US"]
    assert _version(session) == 3

    duplicate_bulk_response = user_list_version_client.post(
        f"/api/v2/user-lists/{list_id}/entries/bulk",
        headers=headers,
        json={"values": ["US", "CA"]},
    )
    assert duplicate_bulk_response.status_code == 201
    assert duplicate_bulk_response.json()["added"] == []
    assert _version(session) == 3

    entry = session.query(UserListEntry).filter(UserListEntry.ul_id == list_id, UserListEntry.entry_value == "CA").one()
    delete_response = user_list_version_client.delete(
        f"/api/v2/user-lists/{list_id}/entries/{entry.ule_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True
    assert _version(session) == 4


def test_api_failed_and_no_op_list_mutations_do_not_increment(user_list_version_client, session):
    headers = _auth_headers(user_list_version_client)
    user_list = _create_user_list(session, name="ExistingCountries")

    duplicate_response = user_list_version_client.post(
        "/api/v2/user-lists",
        headers=headers,
        json={"name": "ExistingCountries"},
    )
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["success"] is False
    assert _version(session) is None

    validation_response = user_list_version_client.post(
        "/api/v2/user-lists",
        headers=headers,
        json={"name": ""},
    )
    assert validation_response.status_code == 422
    assert _version(session) is None

    same_name_response = user_list_version_client.put(
        f"/api/v2/user-lists/{user_list.ul_id}",
        headers=headers,
        json={"name": "ExistingCountries"},
    )
    assert same_name_response.status_code == 200
    assert same_name_response.json()["success"] is True
    assert _version(session) is None

    missing_delete_response = user_list_version_client.delete("/api/v2/user-lists/99999", headers=headers)
    assert missing_delete_response.status_code == 404
    assert _version(session) is None


def test_persistent_manager_mutations_increment_version(session):
    manager = PersistentUserListManager(db_session=session, o_id=1)
    manager._ensure_initialized()
    base_version = _version(session)
    assert base_version == 1

    manager.create_list("ManagerCountries")
    assert _version(session) == base_version + 1

    manager.add_entry("ManagerCountries", "GB")
    assert _version(session) == base_version + 2

    manager.add_entry("ManagerCountries", "GB")
    assert _version(session) == base_version + 2

    manager.remove_entry("ManagerCountries", "GB")
    assert _version(session) == base_version + 3

    manager.remove_entry("ManagerCountries", "GB")
    assert _version(session) == base_version + 3

    manager.delete_list("ManagerCountries")
    assert _version(session) == base_version + 4


def test_demo_user_list_seeding_increments_only_when_seed_data_changes(session):
    manager = PersistentUserListManager(db_session=session, o_id=1)
    manager._ensure_initialized()
    base_version = _version(session)
    assert base_version == 1

    seed_demo_user_lists(manager)
    assert _version(session) == base_version + 1

    seed_demo_user_lists(manager)
    assert _version(session) == base_version + 1
