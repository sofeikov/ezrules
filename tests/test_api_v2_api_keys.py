"""
Tests for API key management and evaluate endpoint hardening.

These tests verify:
- 401 when evaluate is called without credentials
- 401 with an invalid or revoked API key
- 200 with a valid API key
- 200 with a valid Bearer token
- Error sanitisation on evaluate 500
- Body size limit (413)
- API key CRUD: create, list, revoke
"""

import hashlib
import secrets
import uuid

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, ApiKey, Organisation, Role, RoleActions, User


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def org(session):
    return session.query(Organisation).one()


@pytest.fixture(scope="function")
def live_api_key(session, org):
    """Insert an active API key and return the raw key string."""
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="test-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


@pytest.fixture(scope="function")
def admin_user_with_permissions(session):
    """Create an admin user who has MANAGE_API_KEYS permission."""
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()

    hashed_password = bcrypt.hashpw("adminpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = session.query(Role).filter(Role.name == "apikey_admin").first()
    if not role:
        role = Role(name="apikey_admin", description="API key admin")
        session.add(role)
        session.commit()

    # Assign all permissions to the role
    action = session.query(Action).filter(Action.name == PermissionAction.MANAGE_API_KEYS.value).first()
    assert action is not None, "MANAGE_API_KEYS action not initialised"
    existing = session.query(RoleActions).filter_by(role_id=role.id, action_id=action.id).first()
    if not existing:
        session.add(RoleActions(role_id=role.id, action_id=action.id))
        session.commit()

    user = session.query(User).filter(User.email == "apikeyuser@example.com").first()
    if not user:
        user = User(
            email="apikeyuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="apikeyuser@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    return user


@pytest.fixture(scope="function")
def bearer_token(admin_user_with_permissions):
    """Return a valid Bearer access token for the admin user."""
    user = admin_user_with_permissions
    return create_access_token(
        user_id=user.id,
        email=user.email,
        roles=[r.name for r in user.roles],
    )


# =============================================================================
# AUTH TESTS
# =============================================================================


class TestApiKeyAuth:
    """Tests for evaluate endpoint authentication."""

    def test_no_credentials_returns_401(self, session):
        """Evaluate without any credentials should return 401."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "auth_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
            )
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, session):
        """Evaluate with a random unknown key should return 401."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "auth_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": "ezrk_" + "0" * 64},
            )
        assert response.status_code == 401
        assert "Invalid or revoked API key" in response.json()["detail"]

    def test_valid_api_key_returns_200(self, session, live_api_key):
        """Evaluate with a valid API key should succeed."""
        org = session.query(Organisation).one()
        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
        evaluator_router._lre = lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "auth_key_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None
        assert response.status_code == 200

    def test_valid_bearer_token_returns_200(self, session, bearer_token):
        """Evaluate with a valid Bearer token should succeed."""
        org = session.query(Organisation).one()
        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
        evaluator_router._lre = lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "bearer_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"Authorization": f"Bearer {bearer_token}"},
            )

        evaluator_router._lre = None
        assert response.status_code == 200

    def test_invalid_bearer_token_returns_401(self, session):
        """Evaluate with a malformed Bearer token should return 401."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "bad_bearer",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"Authorization": "Bearer totally.invalid.token"},
            )
        assert response.status_code == 401


# =============================================================================
# ERROR SANITISATION TESTS
# =============================================================================


class TestApiKeyErrorSanitisation:
    """Verify that 500 errors from evaluate do not leak internal details."""

    def test_500_error_is_sanitised(self, session, live_api_key, monkeypatch):
        """Force an internal error and check that only a generic message is returned."""
        from ezrules.backend import data_utils

        def exploding_eval(*args, **kwargs):
            raise RuntimeError("secret internal database error with connection string")

        monkeypatch.setattr(data_utils, "eval_and_store", exploding_eval)

        org = session.query(Organisation).one()
        lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
        evaluator_router._lre = lre

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "error_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail == "Evaluation failed"
        assert "secret" not in detail
        assert "database" not in detail


# =============================================================================
# BODY SIZE LIMIT TESTS
# =============================================================================


class TestBodySizeLimit:
    """Verify that oversized request bodies are rejected with 413."""

    def test_oversized_body_returns_413(self, session, live_api_key):
        """A request with Content-Length > MAX_BODY_SIZE_KB * 1024 should return 413."""
        large_size = 2 * 1024 * 1024  # 2 MB — well above the 1 MB default

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                content=b"x" * large_size,
                headers={
                    "X-API-Key": live_api_key,
                    "Content-Type": "application/json",
                    "Content-Length": str(large_size),
                },
            )

        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()


# =============================================================================
# API KEY CRUD TESTS
# =============================================================================


class TestApiKeyCRUD:
    """Tests for POST/GET/DELETE /api/v2/api-keys."""

    def test_create_api_key(self, session, admin_user_with_permissions, bearer_token):
        """Create an API key and verify the raw key is returned once."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/api-keys",
                json={"label": "my-service-key"},
                headers={"Authorization": f"Bearer {bearer_token}"},
            )

        assert response.status_code == 201
        data = response.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("ezrk_")
        assert "gid" in data
        assert data["label"] == "my-service-key"
        assert data["revoked_at"] is None

        # Confirm it's stored in DB with hashed key
        api_key = session.query(ApiKey).filter(ApiKey.gid == data["gid"]).first()
        assert api_key is not None
        assert api_key.key_hash == hashlib.sha256(data["raw_key"].encode()).hexdigest()

    def test_create_api_key_unauthenticated_returns_401(self, session):
        """Creating an API key without auth should return 401."""
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/api-keys",
                json={"label": "no-auth-key"},
            )
        assert response.status_code == 401

    def test_list_api_keys(self, session, admin_user_with_permissions, bearer_token, live_api_key):
        """List should return active keys without raw_key values."""
        with TestClient(app) as client:
            response = client.get(
                "/api/v2/api-keys",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )

        assert response.status_code == 200
        keys = response.json()
        assert len(keys) >= 1
        # raw_key must never appear in listing
        for k in keys:
            assert "raw_key" not in k
            assert "gid" in k
            assert "label" in k

    def test_revoke_api_key(self, session, admin_user_with_permissions, bearer_token):
        """Revoking a key should set revoked_at and reject subsequent auth."""
        # Create a key first
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v2/api-keys",
                json={"label": "revoke-test-key"},
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        assert create_resp.status_code == 201
        gid = create_resp.json()["gid"]
        raw_key = create_resp.json()["raw_key"]

        # Revoke it
        with TestClient(app) as client:
            revoke_resp = client.delete(
                f"/api/v2/api-keys/{gid}",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        assert revoke_resp.status_code == 204

        # Confirm DB row has revoked_at set
        session.expire_all()
        api_key = session.query(ApiKey).filter(ApiKey.gid == gid).first()
        assert api_key is not None
        assert api_key.revoked_at is not None

        # Confirm the revoked key is rejected by evaluate
        with TestClient(app) as client:
            eval_resp = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "revoked_key_test",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": raw_key},
            )
        assert eval_resp.status_code == 401

    def test_revoke_nonexistent_key_returns_404(self, session, admin_user_with_permissions, bearer_token):
        """Revoking an unknown GID should return 404."""
        with TestClient(app) as client:
            response = client.delete(
                "/api/v2/api-keys/00000000-0000-0000-0000-000000000000",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        assert response.status_code == 404

    def test_revoked_key_absent_from_list(self, session, admin_user_with_permissions, bearer_token):
        """After revoking, the key should no longer appear in GET /api/v2/api-keys."""
        # Create and revoke a key
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v2/api-keys",
                json={"label": "disappear-key"},
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        gid = create_resp.json()["gid"]

        with TestClient(app) as client:
            client.delete(f"/api/v2/api-keys/{gid}", headers={"Authorization": f"Bearer {bearer_token}"})

        with TestClient(app) as client:
            list_resp = client.get(
                "/api/v2/api-keys",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )

        gids = [k["gid"] for k in list_resp.json()]
        assert gid not in gids
