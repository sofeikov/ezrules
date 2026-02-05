"""
Tests for FastAPI v2 permission dependencies.

These tests verify:
- require_permission dependency works correctly
- require_any_permission dependency works correctly
- Permission denied returns 403
- Backward compatibility when no actions are configured
"""

import bcrypt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    require_any_permission,
    require_permission,
)
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, Role, RoleActions, User


@pytest.fixture(scope="function")
def permission_test_client(session):
    """
    Create a FastAPI test client with users that have different permission levels.
    """
    hashed_password = bcrypt.hashpw("testpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create roles
    admin_role = session.query(Role).filter(Role.name == "perm_admin").first()
    if not admin_role:
        admin_role = Role(name="perm_admin", description="Admin role for permission tests")
        session.add(admin_role)
        session.commit()

    viewer_role = session.query(Role).filter(Role.name == "perm_viewer").first()
    if not viewer_role:
        viewer_role = Role(name="perm_viewer", description="Viewer role for permission tests")
        session.add(viewer_role)
        session.commit()

    # Create admin user with VIEW_RULES permission
    admin_user = session.query(User).filter(User.email == "permadmin@example.com").first()
    if not admin_user:
        admin_user = User(
            email="permadmin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="permadmin@example.com",
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        session.commit()

    # Create viewer user (no special permissions)
    viewer_user = session.query(User).filter(User.email == "permviewer@example.com").first()
    if not viewer_user:
        viewer_user = User(
            email="permviewer@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="permviewer@example.com",
        )
        viewer_user.roles.append(viewer_role)
        session.add(viewer_user)
        session.commit()

    # Store references for the test
    client_data = {
        "admin_user": admin_user,
        "viewer_user": viewer_user,
        "admin_role": admin_role,
        "viewer_role": viewer_role,
        "session": session,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def setup_permissions(session):
    """
    Initialize the default actions in the database.
    """
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    return session


# =============================================================================
# REQUIRE_PERMISSION DEPENDENCY TESTS
# =============================================================================


class TestRequirePermission:
    """Tests for the require_permission dependency factory."""

    def test_permission_granted(self, permission_test_client, setup_permissions):
        """User with correct permission should be able to access the endpoint."""
        session = permission_test_client.test_data["session"]
        admin_user = permission_test_client.test_data["admin_user"]
        admin_role = permission_test_client.test_data["admin_role"]

        # Grant VIEW_RULES permission to admin role
        PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_RULES)

        # Create token for admin user
        roles = [role.name for role in admin_user.roles]
        token = create_access_token(
            user_id=int(admin_user.id),
            email=str(admin_user.email),
            roles=roles,
        )

        # Access /me endpoint (which is already protected, just testing auth works)
        response = permission_test_client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    def test_permission_denied(self, permission_test_client, setup_permissions):
        """User without permission should get 403."""
        session = permission_test_client.test_data["session"]
        viewer_user = permission_test_client.test_data["viewer_user"]

        # Create token for viewer user (who has no permissions)
        roles = [role.name for role in viewer_user.roles]
        token = create_access_token(
            user_id=int(viewer_user.id),
            email=str(viewer_user.email),
            roles=roles,
        )

        # Create a test app with a protected endpoint
        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.CREATE_RULE)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
            assert "Permission denied" in response.json()["detail"]

    def test_permission_backward_compatibility_no_actions(self, permission_test_client, session):
        """When no actions exist in DB, should allow access (backward compatibility)."""
        # Don't call setup_permissions - no actions in DB
        viewer_user = permission_test_client.test_data["viewer_user"]

        # Create token for viewer user
        roles = [role.name for role in viewer_user.roles]
        token = create_access_token(
            user_id=int(viewer_user.id),
            email=str(viewer_user.email),
            roles=roles,
        )

        # Create a test app with a protected endpoint
        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.CREATE_RULE)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Should be allowed because no actions exist (backward compatibility)
            assert response.status_code == 200

    def test_permission_with_global_permission(self, permission_test_client, setup_permissions):
        """Global permission (no resource_id) should grant access to any resource."""
        session = permission_test_client.test_data["session"]
        admin_user = permission_test_client.test_data["admin_user"]
        admin_role = permission_test_client.test_data["admin_role"]

        # Grant global CREATE_RULE permission (no resource_id)
        PermissionManager.grant_permission(admin_role.id, PermissionAction.CREATE_RULE)

        roles = [role.name for role in admin_user.roles]
        token = create_access_token(
            user_id=int(admin_user.id),
            email=str(admin_user.email),
            roles=roles,
        )

        # Create a test app with a protected endpoint
        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.CREATE_RULE)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200

    def test_permission_nonexistent_action_denies_access(self, permission_test_client, setup_permissions):
        """Action not in DB should deny access (fail secure)."""
        session = permission_test_client.test_data["session"]
        admin_user = permission_test_client.test_data["admin_user"]

        roles = [role.name for role in admin_user.roles]
        token = create_access_token(
            user_id=int(admin_user.id),
            email=str(admin_user.email),
            roles=roles,
        )

        # Create a test app with a protected endpoint using a non-existent action
        test_app = FastAPI()

        # Use a string that doesn't exist as an action
        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission("nonexistent_action")),  # type: ignore
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Should deny access because action doesn't exist
            assert response.status_code == 403


# =============================================================================
# REQUIRE_ANY_PERMISSION DEPENDENCY TESTS
# =============================================================================


class TestRequireAnyPermission:
    """Tests for the require_any_permission dependency factory."""

    def test_any_permission_first_granted(self, permission_test_client, setup_permissions):
        """User with first permission should be allowed."""
        session = permission_test_client.test_data["session"]
        admin_user = permission_test_client.test_data["admin_user"]
        admin_role = permission_test_client.test_data["admin_role"]

        # Grant only VIEW_RULES permission
        PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_RULES)

        roles = [role.name for role in admin_user.roles]
        token = create_access_token(
            user_id=int(admin_user.id),
            email=str(admin_user.email),
            roles=roles,
        )

        # Create a test app that requires VIEW_RULES OR VIEW_OUTCOMES
        test_app = FastAPI()

        @test_app.get("/dashboard")
        def dashboard(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_any_permission(PermissionAction.VIEW_RULES, PermissionAction.VIEW_OUTCOMES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200

    def test_any_permission_second_granted(self, permission_test_client, setup_permissions):
        """User with second permission should be allowed."""
        session = permission_test_client.test_data["session"]
        admin_user = permission_test_client.test_data["admin_user"]
        admin_role = permission_test_client.test_data["admin_role"]

        # Grant only VIEW_OUTCOMES permission (not VIEW_RULES)
        PermissionManager.grant_permission(admin_role.id, PermissionAction.VIEW_OUTCOMES)

        roles = [role.name for role in admin_user.roles]
        token = create_access_token(
            user_id=int(admin_user.id),
            email=str(admin_user.email),
            roles=roles,
        )

        # Create a test app that requires VIEW_RULES OR VIEW_OUTCOMES
        test_app = FastAPI()

        @test_app.get("/dashboard")
        def dashboard(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_any_permission(PermissionAction.VIEW_RULES, PermissionAction.VIEW_OUTCOMES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200

    def test_any_permission_none_granted(self, permission_test_client, setup_permissions):
        """User without any of the required permissions should get 403."""
        session = permission_test_client.test_data["session"]
        viewer_user = permission_test_client.test_data["viewer_user"]

        # Viewer has no permissions
        roles = [role.name for role in viewer_user.roles]
        token = create_access_token(
            user_id=int(viewer_user.id),
            email=str(viewer_user.email),
            roles=roles,
        )

        # Create a test app that requires VIEW_RULES OR VIEW_OUTCOMES
        test_app = FastAPI()

        @test_app.get("/dashboard")
        def dashboard(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_any_permission(PermissionAction.VIEW_RULES, PermissionAction.VIEW_OUTCOMES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
            assert "Permission denied" in response.json()["detail"]

    def test_any_permission_backward_compatibility(self, permission_test_client, session):
        """When no actions exist, should allow access."""
        # Don't initialize actions
        viewer_user = permission_test_client.test_data["viewer_user"]

        roles = [role.name for role in viewer_user.roles]
        token = create_access_token(
            user_id=int(viewer_user.id),
            email=str(viewer_user.email),
            roles=roles,
        )

        test_app = FastAPI()

        @test_app.get("/dashboard")
        def dashboard(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_any_permission(PermissionAction.VIEW_RULES, PermissionAction.VIEW_OUTCOMES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Should be allowed due to backward compatibility
            assert response.status_code == 200


# =============================================================================
# AUTHENTICATION INTEGRATION TESTS
# =============================================================================


class TestPermissionWithAuth:
    """Tests that verify permission checks work with the full auth flow."""

    def test_unauthenticated_request_returns_401(self, permission_test_client, setup_permissions):
        """Request without token should return 401, not 403."""
        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get("/protected")
            # Should be 401 (auth failed) not 403 (permission denied)
            assert response.status_code == 401

    def test_invalid_token_returns_401(self, permission_test_client, setup_permissions):
        """Request with invalid token should return 401."""
        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": "Bearer invalid.token.here"},
            )
            assert response.status_code == 401

    def test_inactive_user_returns_401(self, permission_test_client, setup_permissions):
        """Inactive user should return 401 before permission check."""
        session = permission_test_client.test_data["session"]

        # Create an inactive user
        hashed_password = bcrypt.hashpw("inactivepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        inactive_user = User(
            email="inactiveperm@example.com",
            password=hashed_password,
            active=False,
            fs_uniquifier="inactiveperm@example.com",
        )
        session.add(inactive_user)
        session.commit()

        token = create_access_token(
            user_id=int(inactive_user.id),
            email=str(inactive_user.email),
            roles=[],
        )

        test_app = FastAPI()

        @test_app.get("/protected")
        def protected_endpoint(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
        ):
            return {"message": "success"}

        with TestClient(test_app) as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
            # Should be 401 (user disabled) not 403
            assert response.status_code == 401
