"""
Tests for FastAPI v2 authentication endpoints.

These tests verify:
- Login with valid/invalid credentials
- Token refresh functionality
- Protected endpoint access
- Token expiration handling
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ezrules.backend.api_v2.main import app
from ezrules.models.backend_core import Role, User, UserSession


@pytest.fixture(scope="function")
def api_client(session):
    """
    Create a FastAPI test client with database session configured.

    The session fixture already sets up the test database and configures
    the global db_session to use it.
    """
    # Create a test user with a properly hashed password
    hashed_password = bcrypt.hashpw("testpassword123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Check if user already exists (from other fixture)
    existing_user = session.query(User).filter(User.email == "testuser@example.com").first()
    if not existing_user:
        test_user = User(
            email="testuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="testuser@example.com",
        )
        session.add(test_user)
        session.commit()

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def api_client_with_roles(session):
    """
    Create a FastAPI test client with a user that has roles assigned.
    """
    hashed_password = bcrypt.hashpw("rolepassword".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create a role if it doesn't exist
    admin_role = session.query(Role).filter(Role.name == "test_admin").first()
    if not admin_role:
        admin_role = Role(name="test_admin", description="Test admin role")
        session.add(admin_role)
        session.commit()

    # Create user with role
    existing_user = session.query(User).filter(User.email == "roleuser@example.com").first()
    if not existing_user:
        role_user = User(
            email="roleuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="roleuser@example.com",
        )
        role_user.roles.append(admin_role)
        session.add(role_user)
        session.commit()

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def inactive_user_client(session):
    """
    Create a FastAPI test client with an inactive user.
    """
    hashed_password = bcrypt.hashpw("inactivepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    existing_user = session.query(User).filter(User.email == "inactive@example.com").first()
    if not existing_user:
        inactive_user = User(
            email="inactive@example.com",
            password=hashed_password,
            active=False,  # Inactive!
            fs_uniquifier="inactive@example.com",
        )
        session.add(inactive_user)
        session.commit()

    with TestClient(app) as client:
        yield client


# =============================================================================
# JWT UTILITY FUNCTION TESTS
# =============================================================================


class TestJWTFunctions:
    """Tests for JWT token creation and decoding."""

    def test_create_access_token(self):
        """Access token should contain correct payload."""
        token = create_access_token(user_id=123, email="test@example.com", roles=["admin", "editor"])

        payload = decode_token(token)
        assert payload is not None
        assert payload.user_id == 123
        assert payload.email == "test@example.com"
        assert payload.roles == ["admin", "editor"]
        assert payload.token_type == "access"

    def test_create_refresh_token(self):
        """Refresh token should contain user_id and type."""
        token = create_refresh_token(user_id=456)

        payload = decode_token(token)
        assert payload is not None
        assert payload.user_id == 456
        assert payload.token_type == "refresh"
        # Refresh tokens don't include email or roles
        assert payload.email is None

    def test_decode_invalid_token(self):
        """Invalid tokens should return None."""
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_decode_tampered_token(self):
        """Tampered tokens should return None."""
        # Create a valid token
        token = create_access_token(user_id=1, email="test@example.com", roles=[])

        # Tamper with it more significantly - change multiple characters in the signature
        # The signature is the last part after the last '.'
        parts = token.split(".")
        signature = parts[-1]
        # Reverse the signature to ensure it's definitely different
        tampered_signature = signature[::-1]
        tampered = ".".join(parts[:-1] + [tampered_signature])

        payload = decode_token(tampered)
        assert payload is None


# =============================================================================
# LOGIN ENDPOINT TESTS
# =============================================================================


class TestLoginEndpoint:
    """Tests for POST /api/v2/auth/login."""

    def test_login_valid_credentials(self, api_client, session):
        """Login with valid credentials should return tokens."""
        response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == ACCESS_TOKEN_EXPIRE_MINUTES * 60

        # Verify the access token is valid
        payload = decode_token(data["access_token"])
        assert payload is not None
        assert payload.email == "testuser@example.com"
        assert payload.token_type == "access"

    def test_login_invalid_password(self, api_client, session):
        """Login with wrong password should return 401."""
        response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, api_client, session):
        """Login with non-existent email should return 401."""
        response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "nobody@example.com", "password": "anypassword"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_inactive_user(self, inactive_user_client, session):
        """Login with inactive user should return 401."""
        response = inactive_user_client.post(
            "/api/v2/auth/login",
            data={"username": "inactive@example.com", "password": "inactivepass"},
        )

        assert response.status_code == 401
        assert "disabled" in response.json()["detail"].lower()

    def test_login_updates_login_tracking(self, api_client, session):
        """Login should update last_login_at and login_count."""
        # First login
        api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )

        user = session.query(User).filter(User.email == "testuser@example.com").first()
        first_login_count = user.login_count

        # Second login
        api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )

        session.refresh(user)
        assert user.login_count == first_login_count + 1
        assert user.current_login_at is not None

    def test_login_with_roles(self, api_client_with_roles, session):
        """Login should include user's roles in token."""
        response = api_client_with_roles.post(
            "/api/v2/auth/login",
            data={"username": "roleuser@example.com", "password": "rolepassword"},
        )

        assert response.status_code == 200
        data = response.json()

        payload = decode_token(data["access_token"])
        assert payload is not None
        assert "test_admin" in payload.roles


# =============================================================================
# REFRESH TOKEN ENDPOINT TESTS
# =============================================================================


class TestRefreshEndpoint:
    """Tests for POST /api/v2/auth/refresh."""

    def test_refresh_valid_token(self, api_client, session):
        """Refresh with valid token should return new tokens."""
        # First, login to get tokens
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        original_tokens = login_response.json()

        # Now refresh
        refresh_response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": original_tokens["refresh_token"]},
        )

        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()

        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"
        # Verify the new access token is valid and contains correct data
        payload = decode_token(new_tokens["access_token"])
        assert payload is not None
        assert payload.email == "testuser@example.com"

    def test_refresh_invalid_token(self, api_client, session):
        """Refresh with invalid token should return 401."""
        response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )

        assert response.status_code == 401

    def test_refresh_with_access_token(self, api_client, session):
        """Refresh with access token (wrong type) should return 401."""
        # Login to get tokens
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        # Try to refresh using the access token (should fail)
        response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": tokens["access_token"]},  # Wrong token type!
        )

        assert response.status_code == 401
        assert "Invalid token type" in response.json()["detail"]


# =============================================================================
# ME ENDPOINT TESTS
# =============================================================================


class TestMeEndpoint:
    """Tests for GET /api/v2/auth/me."""

    def test_me_with_valid_token(self, api_client, session):
        """Should return user info with valid token."""
        # Login first
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        # Call /me with access token
        response = api_client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == "testuser@example.com"
        assert data["active"] is True
        assert "id" in data
        assert "roles" in data

    def test_me_without_token(self, api_client, session):
        """Should return 401 without token."""
        response = api_client.get("/api/v2/auth/me")

        assert response.status_code == 401

    def test_me_with_invalid_token(self, api_client, session):
        """Should return 401 with invalid token."""
        response = api_client.get(
            "/api/v2/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401

    def test_me_with_refresh_token(self, api_client, session):
        """Should return 401 when using refresh token instead of access token."""
        # Login first
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        # Try to use refresh token for /me (should fail)
        response = api_client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )

        assert response.status_code == 401

    def test_me_with_roles(self, api_client_with_roles, session):
        """Should include roles in response."""
        # Login
        login_response = api_client_with_roles.post(
            "/api/v2/auth/login",
            data={"username": "roleuser@example.com", "password": "rolepassword"},
        )
        tokens = login_response.json()

        # Call /me
        response = api_client_with_roles.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["roles"]) > 0
        assert any(role["name"] == "test_admin" for role in data["roles"])


# =============================================================================
# SESSION TRACKING TESTS
# =============================================================================


class TestSessionTracking:
    """Tests for server-side refresh token session tracking (UserSession table)."""

    def test_login_creates_session(self, api_client, session):
        """Login should insert a UserSession row for the issued refresh token."""
        response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 200
        tokens = response.json()

        session.expire_all()
        session_row = session.query(UserSession).filter(UserSession.refresh_token == tokens["refresh_token"]).first()
        assert session_row is not None
        assert session_row.expires_at is not None
        assert session_row.user_id is not None

    def test_refresh_rotation_deletes_old_and_creates_new_session(self, api_client, session):
        """Refresh should delete the consumed session and insert a new one."""
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        original_tokens = login_response.json()
        old_refresh_token = original_tokens["refresh_token"]

        refresh_response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()

        session.expire_all()
        # Old session must be gone
        old_session = session.query(UserSession).filter(UserSession.refresh_token == old_refresh_token).first()
        assert old_session is None

        # New session must exist
        new_session = (
            session.query(UserSession).filter(UserSession.refresh_token == new_tokens["refresh_token"]).first()
        )
        assert new_session is not None

    def test_refresh_token_can_only_be_used_once(self, api_client, session):
        """A refresh token should be invalid after it has been used once (rotation)."""
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        original_refresh_token = login_response.json()["refresh_token"]

        # First use — succeeds and rotates the token
        first_refresh = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": original_refresh_token},
        )
        assert first_refresh.status_code == 200

        # Second use of the same (now-deleted) token — must be rejected
        second_refresh = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": original_refresh_token},
        )
        assert second_refresh.status_code == 401

    def test_refresh_revoked_session_returns_401(self, api_client, session):
        """Refresh with a token whose DB session was deleted should return 401."""
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        # Manually revoke the session directly in the database
        session.query(UserSession).filter(UserSession.refresh_token == tokens["refresh_token"]).delete()
        session.commit()

        response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


# =============================================================================
# LOGOUT ENDPOINT TESTS
# =============================================================================


class TestLogoutEndpoint:
    """Tests for POST /api/v2/auth/logout."""

    def test_logout_deletes_session(self, api_client, session):
        """Logout should remove the UserSession row from the database."""
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        logout_response = api_client.post(
            "/api/v2/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["message"] == "Logged out successfully"

        session.expire_all()
        session_row = session.query(UserSession).filter(UserSession.refresh_token == tokens["refresh_token"]).first()
        assert session_row is None

    def test_refresh_after_logout_returns_401(self, api_client, session):
        """After logout, using the old refresh token should return 401."""
        login_response = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens = login_response.json()

        api_client.post(
            "/api/v2/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 401

    def test_logout_without_access_token_returns_401(self, api_client, session):
        """Logout with no Bearer token should be rejected."""
        response = api_client.post(
            "/api/v2/auth/logout",
            json={"refresh_token": "sometoken"},
        )
        assert response.status_code == 401

    def test_logout_does_not_affect_other_sessions(self, api_client, session):
        """Logging out one session must not invalidate other active sessions."""
        login1 = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens1 = login1.json()

        login2 = api_client.post(
            "/api/v2/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword123"},
        )
        tokens2 = login2.json()

        # Logout the first session only
        api_client.post(
            "/api/v2/auth/logout",
            json={"refresh_token": tokens1["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens1['access_token']}"},
        )

        # Second session should still be usable
        refresh_response = api_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": tokens2["refresh_token"]},
        )
        assert refresh_response.status_code == 200
