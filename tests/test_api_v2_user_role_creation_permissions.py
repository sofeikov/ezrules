"""Regression coverage for keeping role assignment out of onboarding flows."""

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import users as users_routes
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Invitation, Role, User


def _create_user_management_token(session, *, email: str, permissions: list[PermissionAction]) -> str:
    hashed_password = bcrypt.hashpw("permissionpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role = Role(name=f"role_{email.split('@')[0]}", description="Scoped user management role", o_id=1)
    user = User(
        email=email,
        password=hashed_password,
        active=True,
        fs_uniquifier=email,
        o_id=1,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)

    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(user.o_id),
    )


def test_create_user_rejects_role_ids_field(session):
    """Account creation must not accept initial role assignments."""
    token = _create_user_management_token(
        session,
        email="create-only@example.com",
        permissions=[PermissionAction.CREATE_USER],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "blocked-create@example.com",
                "password": "password123",
                "role_ids": [1],
            },
        )

    assert response.status_code == 422
    assert session.query(User).filter(User.email == "blocked-create@example.com").first() is None


def test_create_user_without_role_ids_allowed_with_create_user_only(session):
    """CREATE_USER remains sufficient for creating an account without assigning roles."""
    token = _create_user_management_token(
        session,
        email="create-only-without-roles@example.com",
        permissions=[PermissionAction.CREATE_USER],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "allowed-create@example.com",
                "password": "password123",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["user"]["email"] == "allowed-create@example.com"
    assert data["user"]["roles"] == []


def test_invite_user_rejects_role_ids_field(session, monkeypatch):
    """Invitations must not accept initial role assignments."""
    token = _create_user_management_token(
        session,
        email="invite-create-only@example.com",
        permissions=[PermissionAction.CREATE_USER],
    )

    def fail_if_email_sent(email: str, raw_token: str) -> None:
        raise AssertionError("invite email should not be sent")

    monkeypatch.setattr(users_routes, "send_invitation_email", fail_if_email_sent)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/users/invite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "blocked-invite@example.com",
                "role_ids": [1],
            },
        )

    assert response.status_code == 422
    assert session.query(User).filter(User.email == "blocked-invite@example.com").first() is None
    assert session.query(Invitation).filter(Invitation.email == "blocked-invite@example.com").first() is None
