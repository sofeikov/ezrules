import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuntimeSetting, User


@pytest.fixture(scope="function")
def main_rule_execution_settings_client(session):
    hashed_password = bcrypt.hashpw("settingspass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = session.query(Organisation).one()

    role = session.query(Role).filter(Role.name == "main_execution_settings_admin", Role.o_id == org.o_id).first()
    if not role:
        role = Role(
            name="main_execution_settings_admin",
            description="Can manage runtime settings",
            o_id=int(org.o_id),
        )
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "main-execution-settings-admin@example.com").first()
    if not user:
        user = User(
            email="main-execution-settings-admin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="main-execution-settings-admin@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_PERMISSIONS)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client


def test_runtime_settings_default_main_rule_execution_mode(main_rule_execution_settings_client):
    token = main_rule_execution_settings_client.test_data["token"]

    response = main_rule_execution_settings_client.get(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_rule_execution_mode"] == "all_matches"
    assert payload["default_main_rule_execution_mode"] == "all_matches"


def test_runtime_settings_update_persists_main_rule_execution_mode(main_rule_execution_settings_client):
    token = main_rule_execution_settings_client.test_data["token"]
    session = main_rule_execution_settings_client.test_data["session"]
    org = main_rule_execution_settings_client.test_data["org"]

    response = main_rule_execution_settings_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={"main_rule_execution_mode": "first_match"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_rule_execution_mode"] == "first_match"

    stored = (
        session.query(RuntimeSetting)
        .filter(RuntimeSetting.key == "main_rule_execution_mode", RuntimeSetting.o_id == int(org.o_id))
        .one()
    )
    assert stored.value_type == "string"
    assert stored.value == "first_match"
