import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuntimeSetting, StrictModeHistory, User


@pytest.fixture(scope="function")
def strict_mode_client(session):
    hashed_password = bcrypt.hashpw("strictmodepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = session.query(Organisation).one()

    role = session.query(Role).filter(Role.name == "strict_mode_admin", Role.o_id == org.o_id).first()
    if not role:
        role = Role(
            name="strict_mode_admin",
            description="Can manage strict mode runtime settings and audit",
            o_id=int(org.o_id),
        )
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "strict-mode-admin@example.com").first()
    if not user:
        user = User(
            email="strict-mode-admin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="strict-mode-admin@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_PERMISSIONS)
    PermissionManager.grant_permission(role.id, PermissionAction.ACCESS_AUDIT_TRAIL)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org, "user": user}  # type: ignore[attr-defined]
        yield client


def test_runtime_settings_default_strict_mode_disabled(strict_mode_client):
    token = strict_mode_client.test_data["token"]

    response = strict_mode_client.get(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strict_mode_enabled"] is False
    assert payload["default_strict_mode_enabled"] is False


def test_runtime_settings_update_persists_strict_mode_enabled_and_writes_audit(strict_mode_client):
    token = strict_mode_client.test_data["token"]
    session = strict_mode_client.test_data["session"]
    org = strict_mode_client.test_data["org"]

    response = strict_mode_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={"strict_mode_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strict_mode_enabled"] is True

    stored = (
        session.query(RuntimeSetting)
        .filter(RuntimeSetting.key == "strict_mode_enabled", RuntimeSetting.o_id == int(org.o_id))
        .one()
    )
    assert stored.value_type == "bool"
    assert stored.value == "true"

    history = (
        session.query(StrictModeHistory)
        .filter(StrictModeHistory.o_id == int(org.o_id))
        .order_by(StrictModeHistory.id.desc())
        .first()
    )
    assert history is not None
    assert history.enabled is True
    assert history.action == "enabled"
    assert history.changed_by == "strict-mode-admin@example.com"
    assert history.details == "strict_mode_enabled: false -> true"


def test_runtime_settings_disabling_strict_mode_writes_audit_entry(strict_mode_client):
    token = strict_mode_client.test_data["token"]
    session = strict_mode_client.test_data["session"]
    org = strict_mode_client.test_data["org"]

    enable_response = strict_mode_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={"strict_mode_enabled": True},
    )
    assert enable_response.status_code == 200

    disable_response = strict_mode_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={"strict_mode_enabled": False},
    )

    assert disable_response.status_code == 200
    payload = disable_response.json()
    assert payload["strict_mode_enabled"] is False

    history = (
        session.query(StrictModeHistory)
        .filter(StrictModeHistory.o_id == int(org.o_id))
        .order_by(StrictModeHistory.id.asc())
        .all()
    )
    assert [item.action for item in history] == ["enabled", "disabled"]
    assert history[-1].enabled is False
    assert history[-1].details == "strict_mode_enabled: true -> false"


def test_list_strict_mode_history_is_org_scoped(strict_mode_client):
    token = strict_mode_client.test_data["token"]
    session = strict_mode_client.test_data["session"]
    org = strict_mode_client.test_data["org"]

    other_org = Organisation(name="strict-mode-audit-other")
    session.add(other_org)
    session.commit()

    session.add_all(
        [
            StrictModeHistory(
                enabled=True,
                action="enabled",
                details="strict_mode_enabled: false -> true",
                o_id=int(org.o_id),
                changed_by="strict-mode-admin@example.com",
            ),
            StrictModeHistory(
                enabled=True,
                action="enabled",
                details="strict_mode_enabled: false -> true",
                o_id=int(other_org.o_id),
                changed_by="other@example.com",
            ),
        ]
    )
    session.commit()

    response = strict_mode_client.get(
        "/api/v2/audit/strict-mode",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "enabled"
    assert payload["items"][0]["changed_by"] == "strict-mode-admin@example.com"


def test_audit_summary_includes_total_strict_mode_actions(strict_mode_client):
    token = strict_mode_client.test_data["token"]

    enable_response = strict_mode_client.put(
        "/api/v2/settings/runtime",
        headers={"Authorization": f"Bearer {token}"},
        json={"strict_mode_enabled": True},
    )
    assert enable_response.status_code == 200

    response = strict_mode_client.get(
        "/api/v2/audit",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_strict_mode_actions"] == 1
