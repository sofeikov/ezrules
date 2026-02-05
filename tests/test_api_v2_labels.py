"""
Tests for FastAPI v2 labels endpoints.

These tests verify:
- CRUD operations for labels
- Bulk label creation
- Mark event functionality
- Permission checks
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, Organisation, Role, TestingRecordLog, User


@pytest.fixture(scope="function")
def labels_test_client(session):
    """
    Create a FastAPI test client with a user that has label permissions.
    """
    hashed_password = bcrypt.hashpw("labelpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with label permissions
    label_role = session.query(Role).filter(Role.name == "label_manager").first()
    if not label_role:
        label_role = Role(name="label_manager", description="Can manage labels")
        session.add(label_role)
        session.commit()

    # Create user with role
    label_user = session.query(User).filter(User.email == "labeluser@example.com").first()
    if not label_user:
        label_user = User(
            email="labeluser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="labeluser@example.com",
        )
        label_user.roles.append(label_role)
        session.add(label_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(label_role.id, PermissionAction.VIEW_LABELS)
    PermissionManager.grant_permission(label_role.id, PermissionAction.CREATE_LABEL)
    PermissionManager.grant_permission(label_role.id, PermissionAction.DELETE_LABEL)

    # Create a token for the user
    roles = [role.name for role in label_user.roles]
    token = create_access_token(
        user_id=int(label_user.id),
        email=str(label_user.email),
        roles=roles,
    )

    client_data = {
        "user": label_user,
        "role": label_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_label(session):
    """Create a sample label for testing."""
    label = Label(label="TEST_LABEL")
    session.add(label)
    session.commit()
    return label


@pytest.fixture(scope="function")
def sample_event(session):
    """Create a sample event for testing mark-event functionality."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    event = TestingRecordLog(
        event_id="test_event_123",
        event={"amount": 100, "currency": "USD"},
        event_timestamp=1234567890,
        o_id=org.o_id,
    )
    session.add(event)
    session.commit()
    return event


# =============================================================================
# LIST LABELS TESTS
# =============================================================================


class TestListLabels:
    """Tests for GET /api/v2/labels."""

    def test_list_labels_empty(self, labels_test_client):
        """Should return empty list when no labels exist."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.get(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert isinstance(data["labels"], list)

    def test_list_labels_with_labels(self, labels_test_client, sample_label):
        """Should return list of labels."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.get(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["labels"]) >= 1

        # Find our test label
        test_label = next((lbl for lbl in data["labels"] if lbl["label"] == "TEST_LABEL"), None)
        assert test_label is not None

    def test_list_labels_unauthorized(self, labels_test_client):
        """Should return 401 without token."""
        response = labels_test_client.get("/api/v2/labels")
        assert response.status_code == 401


# =============================================================================
# CREATE LABEL TESTS
# =============================================================================


class TestCreateLabel:
    """Tests for POST /api/v2/labels."""

    def test_create_label_success(self, labels_test_client):
        """Should create a new label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"label_name": "new_label"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["label"]["label"] == "NEW_LABEL"  # Should be uppercase

    def test_create_label_uppercase_conversion(self, labels_test_client):
        """Should convert label name to uppercase."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"label_name": "MixedCase"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["label"]["label"] == "MIXEDCASE"

    def test_create_duplicate_label(self, labels_test_client, sample_label):
        """Should return error for duplicate label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"label_name": "TEST_LABEL"},
        )

        assert response.status_code == 201  # Returns 201 but success=False
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_label_missing_name(self, labels_test_client):
        """Should return 422 for missing label_name."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        assert response.status_code == 422

    def test_create_label_empty_name(self, labels_test_client):
        """Should return 422 for empty label_name."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"label_name": ""},
        )

        assert response.status_code == 422


# =============================================================================
# BULK CREATE LABELS TESTS
# =============================================================================


class TestBulkCreateLabels:
    """Tests for POST /api/v2/labels/bulk."""

    def test_bulk_create_labels_success(self, labels_test_client):
        """Should create multiple labels."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/bulk",
            headers={"Authorization": f"Bearer {token}"},
            json={"labels": ["LABEL_A", "LABEL_B", "LABEL_C"]},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert len(data["created"]) == 3
        assert len(data["failed"]) == 0

    def test_bulk_create_labels_partial_failure(self, labels_test_client, sample_label):
        """Should handle partial failures in bulk create."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/bulk",
            headers={"Authorization": f"Bearer {token}"},
            json={"labels": ["NEW_LABEL_X", "TEST_LABEL", "NEW_LABEL_Y"]},  # TEST_LABEL exists
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is False  # Has failures
        assert len(data["created"]) == 2
        assert len(data["failed"]) == 1
        assert "TEST_LABEL" in data["failed"]


# =============================================================================
# DELETE LABEL TESTS
# =============================================================================


class TestDeleteLabel:
    """Tests for DELETE /api/v2/labels/{label_name}."""

    def test_delete_label_success(self, labels_test_client, sample_label):
        """Should delete existing label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.delete(
            "/api/v2/labels/TEST_LABEL",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

    def test_delete_label_case_insensitive(self, labels_test_client, sample_label):
        """Should delete label regardless of case."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.delete(
            "/api/v2/labels/test_label",  # lowercase
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_delete_nonexistent_label(self, labels_test_client):
        """Should return 404 for non-existent label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.delete(
            "/api/v2/labels/DOES_NOT_EXIST",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


# =============================================================================
# MARK EVENT TESTS
# =============================================================================


class TestMarkEvent:
    """Tests for POST /api/v2/labels/mark-event."""

    def test_mark_event_success(self, labels_test_client, sample_label, sample_event):
        """Should mark an event with a label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "event_id": "test_event_123",
                "label_name": "TEST_LABEL",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["event_id"] == "test_event_123"
        assert data["label_name"] == "TEST_LABEL"

    def test_mark_event_nonexistent_event(self, labels_test_client, sample_label):
        """Should return 404 for non-existent event."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "event_id": "nonexistent_event",
                "label_name": "TEST_LABEL",
            },
        )

        assert response.status_code == 404
        assert "Event" in response.json()["detail"]

    def test_mark_event_nonexistent_label(self, labels_test_client, sample_event):
        """Should return 404 for non-existent label."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "event_id": "test_event_123",
                "label_name": "NONEXISTENT_LABEL",
            },
        )

        assert response.status_code == 404
        assert "Label" in response.json()["detail"]

    def test_mark_event_missing_fields(self, labels_test_client):
        """Should return 422 for missing required fields."""
        token = labels_test_client.test_data["token"]

        response = labels_test_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={"event_id": "some_event"},  # Missing label_name
        )

        assert response.status_code == 422


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestLabelPermissions:
    """Tests for permission checks on label endpoints."""

    def test_view_labels_without_permission(self, session):
        """User without VIEW_LABELS permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_label@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_label@example.com",
        )
        session.add(no_perm_user)
        session.commit()

        # Initialize permissions (but don't grant any to this user)
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        token = create_access_token(
            user_id=int(no_perm_user.id),
            email=str(no_perm_user.email),
            roles=[],
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v2/labels",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_create_label_without_permission(self, session):
        """User without CREATE_LABEL permission should get 403."""
        hashed_password = bcrypt.hashpw("nocreatepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="label_viewer", description="Can only view labels")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly_label@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly_label@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_LABELS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/labels",
                headers={"Authorization": f"Bearer {token}"},
                json={"label_name": "UNAUTHORIZED"},
            )

            assert response.status_code == 403

    def test_delete_label_without_permission(self, session, sample_label):
        """User without DELETE_LABEL permission should get 403."""
        hashed_password = bcrypt.hashpw("nodeletepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW permission
        view_only_role = Role(name="label_viewer_only", description="Can only view labels")
        session.add(view_only_role)
        session.commit()

        # Create user with view-only role
        view_only_user = User(
            email="viewonly2_label@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="viewonly2_label@example.com",
        )
        view_only_user.roles.append(view_only_role)
        session.add(view_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(view_only_role.id, PermissionAction.VIEW_LABELS)

        token = create_access_token(
            user_id=int(view_only_user.id),
            email=str(view_only_user.email),
            roles=[view_only_role.name],
        )

        with TestClient(app) as client:
            response = client.delete(
                f"/api/v2/labels/{sample_label.label}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
