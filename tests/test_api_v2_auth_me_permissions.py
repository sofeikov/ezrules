"""
Tests for permission exposure on GET /api/v2/auth/me.
"""

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Role, User


def test_me_includes_effective_permissions(session):
    hashed_password = bcrypt.hashpw("authmepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = session.query(Role).filter(Role.name == "auth_me_permission_role").first()
    if not role:
        role = Role(name="auth_me_permission_role", description="Role for auth me permission test")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "authme@example.com").first()
    if not user:
        user = User(
            email="authme@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="authme@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.PROMOTE_RULES)

    with TestClient(app) as client:
        login_response = client.post(
            "/api/v2/auth/login",
            data={"username": "authme@example.com", "password": "authmepass"},
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        me_response = client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert me_response.status_code == 200
    data = me_response.json()
    assert data["permissions"] == ["promote_rules", "view_rules"]
