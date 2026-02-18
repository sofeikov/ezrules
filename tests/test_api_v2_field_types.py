"""
Tests for FastAPI v2 field type configuration endpoints.

These tests verify:
- CRUD operations for FieldTypeConfig
- Observations listing
- Upsert behaviour on POST
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import FieldObservation, FieldTypeConfig, Organisation, Role, User


@pytest.fixture(scope="function")
def field_types_client(session):
    """Test client with a user that has all field type permissions."""
    hashed_password = bcrypt.hashpw("ftpass".encode(), bcrypt.gensalt()).decode()

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "field_type_manager").first()
    if not role:
        role = Role(name="field_type_manager", description="Manages field types")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "ft_user@example.com").first()
    if not user:
        user = User(
            email="ft_user@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="ft_user@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.DELETE_FIELD_TYPE)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name])

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_config(session):
    """Create a sample FieldTypeConfig for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    config = FieldTypeConfig(field_name="amount", configured_type="float", o_id=org.o_id)
    session.add(config)
    session.commit()
    return config


@pytest.fixture(scope="function")
def sample_observation(session):
    """Create a sample FieldObservation for testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    obs = FieldObservation(field_name="country", observed_json_type="str", occurrence_count=5, o_id=org.o_id)
    session.add(obs)
    session.commit()
    return obs


# =============================================================================
# LIST CONFIGS
# =============================================================================


class TestListFieldTypeConfigs:
    def test_list_empty(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.get("/api/v2/field-types", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["configs"] == []

    def test_list_with_config(self, field_types_client, sample_config):
        token = field_types_client.test_data["token"]
        response = field_types_client.get("/api/v2/field-types", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        configs = response.json()["configs"]
        assert any(c["field_name"] == "amount" and c["configured_type"] == "float" for c in configs)

    def test_list_requires_auth(self, field_types_client):
        response = field_types_client.get("/api/v2/field-types")
        assert response.status_code == 401


# =============================================================================
# LIST OBSERVATIONS
# =============================================================================


class TestListFieldObservations:
    def test_list_empty(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.get(
            "/api/v2/field-types/observations", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["observations"] == []

    def test_list_with_observation(self, field_types_client, sample_observation):
        token = field_types_client.test_data["token"]
        response = field_types_client.get(
            "/api/v2/field-types/observations", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        obs = response.json()["observations"]
        assert any(o["field_name"] == "country" and o["observed_json_type"] == "str" for o in obs)


# =============================================================================
# CREATE / UPSERT
# =============================================================================


class TestUpsertFieldTypeConfig:
    def test_create_new_config(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.post(
            "/api/v2/field-types",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "score", "configured_type": "integer"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["config"]["field_name"] == "score"
        assert data["config"]["configured_type"] == "integer"

    def test_create_datetime_config_with_format(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.post(
            "/api/v2/field-types",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "event_ts", "configured_type": "datetime", "datetime_format": "%d/%m/%Y"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["config"]["datetime_format"] == "%d/%m/%Y"

    def test_upsert_updates_existing(self, field_types_client, sample_config):
        token = field_types_client.test_data["token"]
        response = field_types_client.post(
            "/api/v2/field-types",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "amount", "configured_type": "integer"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["config"]["configured_type"] == "integer"
        assert "updated" in data["message"]

    def test_create_invalid_type_rejected(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.post(
            "/api/v2/field-types",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "score", "configured_type": "banana"},
        )
        assert response.status_code == 422

    def test_create_requires_auth(self, field_types_client):
        response = field_types_client.post(
            "/api/v2/field-types", json={"field_name": "score", "configured_type": "integer"}
        )
        assert response.status_code == 401


# =============================================================================
# UPDATE
# =============================================================================


class TestUpdateFieldTypeConfig:
    def test_update_existing_config(self, field_types_client, sample_config):
        token = field_types_client.test_data["token"]
        response = field_types_client.put(
            "/api/v2/field-types/amount",
            headers={"Authorization": f"Bearer {token}"},
            json={"configured_type": "string"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["config"]["configured_type"] == "string"

    def test_update_nonexistent_returns_404(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.put(
            "/api/v2/field-types/no_such_field",
            headers={"Authorization": f"Bearer {token}"},
            json={"configured_type": "integer"},
        )
        assert response.status_code == 404


# =============================================================================
# DELETE
# =============================================================================


class TestDeleteFieldTypeConfig:
    def test_delete_existing_config(self, field_types_client, sample_config):
        token = field_types_client.test_data["token"]
        response = field_types_client.delete("/api/v2/field-types/amount", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Confirm it's gone
        list_response = field_types_client.get("/api/v2/field-types", headers={"Authorization": f"Bearer {token}"})
        configs = list_response.json()["configs"]
        assert not any(c["field_name"] == "amount" for c in configs)

    def test_delete_nonexistent_returns_404(self, field_types_client):
        token = field_types_client.test_data["token"]
        response = field_types_client.delete(
            "/api/v2/field-types/no_such_field", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404


# =============================================================================
# PERMISSIONS
# =============================================================================


class TestFieldTypePermissions:
    def test_view_without_permission_returns_403(self, session):
        hashed_password = bcrypt.hashpw("noperm".encode(), bcrypt.gensalt()).decode()
        user = User(
            email="noperm_ft@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_ft@example.com",
        )
        session.add(user)
        session.commit()

        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[])
        with TestClient(app) as client:
            response = client.get("/api/v2/field-types", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 403

    def test_modify_without_permission_returns_403(self, session):
        hashed_password = bcrypt.hashpw("viewonly_ft".encode(), bcrypt.gensalt()).decode()
        role = Role(name="ft_viewer_only", description="View only")
        session.add(role)
        session.commit()

        user = User(
            email="viewonly_ft@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_ft@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_FIELD_TYPES)

        token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name])
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/field-types",
                headers={"Authorization": f"Bearer {token}"},
                json={"field_name": "amount", "configured_type": "float"},
            )
            assert response.status_code == 403
