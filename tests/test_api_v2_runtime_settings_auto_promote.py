"""Tests for the active-rule auto-promotion runtime setting."""

import bcrypt

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuntimeSetting, User
from ezrules.settings import app_settings


def _get_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


@pytest.fixture(scope="function")
def runtime_settings_auto_promote_client(session):
    hashed_password = bcrypt.hashpw("settingspass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = _get_org(session)

    role = session.query(Role).filter(Role.name == "runtime_settings_admin", Role.o_id == int(org.o_id)).first()
    if role is None:
        role = Role(name="runtime_settings_admin", description="Can manage runtime settings", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "runtime-settings-admin@example.com").first()
    if user is None:
        user = User(
            email="runtime-settings-admin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="runtime-settings-admin@example.com",
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
        client.test_data = {
            "token": token,
            "session": session,
            "org": org,
        }  # type: ignore[attr-defined]
        yield client


def test_runtime_settings_defaults_include_active_rule_auto_promote(runtime_settings_auto_promote_client):
    token = runtime_settings_auto_promote_client.test_data["token"]

    response = runtime_settings_auto_promote_client.get(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_promote_active_rule_updates"] is False
    assert payload["default_auto_promote_active_rule_updates"] is False
    assert payload["rule_quality_lookback_days"] == app_settings.RULE_QUALITY_LOOKBACK_DAYS


def test_runtime_settings_update_persists_active_rule_auto_promote(runtime_settings_auto_promote_client):
    token = runtime_settings_auto_promote_client.test_data["token"]
    session = runtime_settings_auto_promote_client.test_data["session"]
    org = runtime_settings_auto_promote_client.test_data["org"]

    response = runtime_settings_auto_promote_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_quality_lookback_days": 14,
            "auto_promote_active_rule_updates": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_quality_lookback_days"] == 14
    assert payload["auto_promote_active_rule_updates"] is True

    stored = (
        session.query(RuntimeSetting)
        .filter(
            RuntimeSetting.key == "auto_promote_active_rule_updates",
            RuntimeSetting.o_id == int(org.o_id),
        )
        .one()
    )
    assert stored.value_type == "bool"
    assert stored.value == "true"
