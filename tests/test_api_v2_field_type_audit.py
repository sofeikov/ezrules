"""
Tests for field type config audit trail recording.

These tests verify:
- Audit entries are recorded for field type create/update/delete actions
- GET /api/v2/audit/field-types returns correct history
- Filtering by field_name works
- AuditSummaryResponse includes total_field_type_actions
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import FieldTypeHistory, Organisation, Role, User


@pytest.fixture(scope="function")
def ft_audit_client(session):
    """Test client with a user that has field type + audit trail permissions."""
    hashed_password = bcrypt.hashpw("ftauditpass".encode(), bcrypt.gensalt()).decode()

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "ft_audit_manager").first()
    if not role:
        role = Role(name="ft_audit_manager", description="Manages field types and can audit")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "ft_audit@example.com").first()
    if not user:
        user = User(
            email="ft_audit@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="ft_audit@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_FIELD_TYPES)
    PermissionManager.grant_permission(role.id, PermissionAction.DELETE_FIELD_TYPE)
    PermissionManager.grant_permission(role.id, PermissionAction.ACCESS_AUDIT_TRAIL)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name])

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore
        yield client


# =============================================================================
# AUDIT RECORDING TESTS
# =============================================================================


class TestFieldTypeAuditRecording:
    """Tests that audit entries are recorded on field type config mutations."""

    def test_create_records_audit_entry(self, ft_audit_client):
        """POST should record a 'created' audit entry."""
        token = ft_audit_client.test_data["token"]
        session = ft_audit_client.test_data["session"]

        field_name = "audit_create_test_amount"
        response = ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "integer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

        entry = (
            session.query(FieldTypeHistory)
            .filter(FieldTypeHistory.field_name == field_name, FieldTypeHistory.action == "created")
            .first()
        )
        assert entry is not None
        assert entry.configured_type == "integer"
        assert entry.changed_by == "ft_audit@example.com"

    def test_update_via_post_records_audit_entry(self, ft_audit_client):
        """POST on existing field should record an 'updated' audit entry."""
        token = ft_audit_client.test_data["token"]
        session = ft_audit_client.test_data["session"]

        field_name = "audit_update_post_amount"
        # First create
        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Now update via POST (upsert path)
        response = ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "integer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

        updated_entry = (
            session.query(FieldTypeHistory)
            .filter(FieldTypeHistory.field_name == field_name, FieldTypeHistory.action == "updated")
            .first()
        )
        assert updated_entry is not None
        assert updated_entry.configured_type == "integer"

    def test_put_records_audit_entry(self, ft_audit_client):
        """PUT should record an 'updated' audit entry."""
        token = ft_audit_client.test_data["token"]
        session = ft_audit_client.test_data["session"]

        field_name = "audit_put_amount"
        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = ft_audit_client.put(
            f"/api/v2/field-types/{field_name}",
            json={"configured_type": "float"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        entry = (
            session.query(FieldTypeHistory)
            .filter(FieldTypeHistory.field_name == field_name, FieldTypeHistory.action == "updated")
            .first()
        )
        assert entry is not None
        assert entry.configured_type == "float"

    def test_delete_records_audit_entry(self, ft_audit_client):
        """DELETE should record a 'deleted' audit entry with the old type."""
        token = ft_audit_client.test_data["token"]
        session = ft_audit_client.test_data["session"]

        field_name = "audit_delete_amount"
        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "boolean"},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = ft_audit_client.delete(
            f"/api/v2/field-types/{field_name}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        entry = (
            session.query(FieldTypeHistory)
            .filter(FieldTypeHistory.field_name == field_name, FieldTypeHistory.action == "deleted")
            .first()
        )
        assert entry is not None
        assert entry.configured_type == "boolean"


# =============================================================================
# FIELD TYPE HISTORY ENDPOINT TESTS
# =============================================================================


class TestFieldTypeHistoryEndpoint:
    """Tests for GET /api/v2/audit/field-types."""

    def test_list_field_type_history_empty(self, ft_audit_client):
        """Should return empty list when no history exists for a specific field."""
        token = ft_audit_client.test_data["token"]

        response = ft_audit_client.get(
            "/api/v2/audit/field-types?field_name=nonexistent_field_xyz",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_field_type_history_returns_entries(self, ft_audit_client):
        """Should return audit entries after creating a field type config."""
        token = ft_audit_client.test_data["token"]

        field_name = "hist_endpoint_amount"
        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "integer"},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = ft_audit_client.get(
            f"/api/v2/audit/field-types?field_name={field_name}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item["action"] == "created" for item in data["items"])

    def test_list_field_type_history_pagination(self, ft_audit_client):
        """Should respect limit and offset pagination."""
        token = ft_audit_client.test_data["token"]

        response = ft_audit_client.get(
            "/api/v2/audit/field-types?limit=5&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["items"]) <= 5

    def test_list_field_type_history_item_shape(self, ft_audit_client):
        """Returned items should have the expected fields."""
        token = ft_audit_client.test_data["token"]

        field_name = "hist_shape_amount"
        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": field_name, "configured_type": "float"},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = ft_audit_client.get(
            f"/api/v2/audit/field-types?field_name={field_name}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        item = items[0]
        assert "id" in item
        assert "field_name" in item
        assert "configured_type" in item
        assert "action" in item
        assert "changed" in item
        assert "changed_by" in item

    def test_list_field_type_history_unauthorized(self, ft_audit_client):
        """Should return 401 without a token."""
        response = ft_audit_client.get("/api/v2/audit/field-types")
        assert response.status_code == 401


# =============================================================================
# AUDIT SUMMARY TESTS
# =============================================================================


class TestAuditSummaryIncludesFieldTypes:
    """Tests that the audit summary includes total_field_type_actions."""

    def test_audit_summary_has_field_type_count(self, ft_audit_client):
        """GET /api/v2/audit should include total_field_type_actions."""
        token = ft_audit_client.test_data["token"]

        response = ft_audit_client.get(
            "/api/v2/audit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_field_type_actions" in data
        assert isinstance(data["total_field_type_actions"], int)

    def test_audit_summary_field_type_count_increments(self, ft_audit_client):
        """Creating a field type config should increment total_field_type_actions."""
        token = ft_audit_client.test_data["token"]

        before = ft_audit_client.get(
            "/api/v2/audit",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["total_field_type_actions"]

        ft_audit_client.post(
            "/api/v2/field-types",
            json={"field_name": "summary_count_amount", "configured_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )

        after = ft_audit_client.get(
            "/api/v2/audit",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["total_field_type_actions"]

        assert after == before + 1
