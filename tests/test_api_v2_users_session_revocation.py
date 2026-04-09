"""
Regression tests for session revocation in admin user updates.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, User, UserSession


@pytest.fixture(scope="function")
def user_admin_client(session):
    """Create a FastAPI client for a user admin."""
    hashed_password = bcrypt.hashpw("adminpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    assert org is not None

    admin_role = session.query(Role).filter(Role.name == "user_admin").first()
    if not admin_role:
        admin_role = Role(name="user_admin", description="Can manage users")
        session.add(admin_role)
        session.commit()

    admin_user = session.query(User).filter(User.email == "useradmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="useradmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="useradmin@example.com",
            o_id=int(org.o_id),
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(admin_role.id, PermissionAction.MODIFY_USER)

    token = create_access_token(
        user_id=int(admin_user.id),
        email=str(admin_user.email),
        roles=[role.name for role in admin_user.roles],
        org_id=int(admin_user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"session": session, "token": token, "user": admin_user}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def managed_user(session):
    """Create a target user whose password is managed by an admin."""
    hashed_password = bcrypt.hashpw("samplepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        email="managed-user@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="managed-user@example.com",
        o_id=1,
    )
    session.add(user)
    session.commit()
    return user


def test_admin_password_change_revokes_existing_refresh_sessions(user_admin_client, managed_user):
    """Changing a user's password through the admin route should revoke their active sessions."""
    session = user_admin_client.test_data["session"]
    token = user_admin_client.test_data["token"]
    admin_user = user_admin_client.test_data["user"]
    managed_user_id = int(managed_user.id)
    admin_user_id = int(admin_user.id)
    new_password = "newpassword123"
    now = datetime.now(UTC).replace(tzinfo=None)
    session_expires_at = now + timedelta(days=7)

    session.add_all(
        [
            UserSession(
                user_id=managed_user_id,
                refresh_token="managed-refresh-token-1",
                expires_at=session_expires_at,
            ),
            UserSession(
                user_id=managed_user_id,
                refresh_token="managed-refresh-token-2",
                expires_at=session_expires_at,
            ),
            UserSession(
                user_id=admin_user_id,
                refresh_token="admin-refresh-token",
                expires_at=session_expires_at,
            ),
        ]
    )
    session.commit()

    response = user_admin_client.put(
        f"/api/v2/users/{managed_user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": new_password},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    session.refresh(managed_user)

    assert bcrypt.checkpw(new_password.encode("utf-8"), managed_user.password.encode("utf-8"))
    assert session.query(UserSession).filter(UserSession.user_id == managed_user_id).count() == 0
    assert session.query(UserSession).filter(UserSession.user_id == admin_user_id).count() == 1
