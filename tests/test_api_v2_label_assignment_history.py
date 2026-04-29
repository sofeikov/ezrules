import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    EventVersionLabel,
    Label,
    LabelHistory,
    Organisation,
    Role,
    User,
)
from tests.canonical_helpers import add_served_decision


def _get_org(session) -> Organisation:
    return session.query(Organisation).one()


@pytest.fixture(scope="function")
def label_audit_client(session):
    org = _get_org(session)

    hashed_password = bcrypt.hashpw("labelauditpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = session.query(Role).filter(Role.name == "label_audit_manager", Role.o_id == org.o_id).first()
    if not role:
        role = Role(name="label_audit_manager", description="Can manage labels and audit", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "labelaudit@example.com").first()
    if not user:
        user = User(
            email="labelaudit@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="labelaudit@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_LABELS)
    PermissionManager.grant_permission(role.id, PermissionAction.CREATE_LABEL)
    PermissionManager.grant_permission(role.id, PermissionAction.ACCESS_AUDIT_TRAIL)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org, "user": user}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def audit_label(session):
    org = _get_org(session)
    label = Label(label="AUDIT_LABEL", o_id=int(org.o_id))
    session.add(label)
    session.commit()
    return label


@pytest.fixture(scope="function")
def audit_event(session):
    org = _get_org(session)

    decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id="audit_event_123",
        event_timestamp=1234567890,
        event_data={"amount": 100, "currency": "USD"},
    )
    session.commit()
    return decision


class TestLabelAssignmentAudit:
    def test_mark_event_records_assignment_history(self, label_audit_client, audit_label, audit_event):
        token = label_audit_client.test_data["token"]
        session = label_audit_client.test_data["session"]

        response = label_audit_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={"event_id": audit_event.event_id, "label_name": audit_label.label},
        )

        assert response.status_code == 200

        history_entries = session.query(LabelHistory).order_by(LabelHistory.id.asc()).all()
        assert len(history_entries) == 1
        assert history_entries[0].action == "assigned"
        assert history_entries[0].label == audit_label.label
        assert history_entries[0].details == f"Event ID: {audit_event.event_id}, event version: 1"
        assert history_entries[0].changed_by == "labelaudit@example.com"

    def test_upload_records_history_only_for_successful_rows_and_exposes_details_in_audit(
        self, label_audit_client, audit_label, audit_event
    ):
        token = label_audit_client.test_data["token"]
        session = label_audit_client.test_data["session"]

        csv_content = f"{audit_event.event_id},{audit_label.label}\nmissing_event,{audit_label.label}\n"

        upload_response = label_audit_client.post(
            "/api/v2/labels/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("labels.csv", csv_content, "text/csv")},
        )

        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        assert upload_data["successful"] == 1
        assert upload_data["failed"] == 1

        history_entries = session.query(LabelHistory).order_by(LabelHistory.id.asc()).all()
        assert len(history_entries) == 1
        assert history_entries[0].action == "assigned_via_csv"
        assert history_entries[0].details == f"Event ID: {audit_event.event_id}, event version: 1"

        audit_response = label_audit_client.get(
            "/api/v2/audit/labels",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert audit_response.status_code == 200
        audit_data = audit_response.json()
        assert audit_data["total"] == 1
        assert audit_data["items"][0]["action"] == "assigned_via_csv"
        assert audit_data["items"][0]["details"] == f"Event ID: {audit_event.event_id}, event version: 1"

    def test_mark_event_labels_latest_duplicate_event_id_version(self, label_audit_client, audit_label):
        token = label_audit_client.test_data["token"]
        session = label_audit_client.test_data["session"]
        org = label_audit_client.test_data["org"]

        add_served_decision(
            session,
            org_id=int(org.o_id),
            event_id="duplicate_mark_event",
            event_timestamp=1234567890,
            event_data={"amount": 100},
        )
        latest_decision = add_served_decision(
            session,
            org_id=int(org.o_id),
            event_id="duplicate_mark_event",
            event_timestamp=1234567891,
            event_data={"amount": 200},
        )
        session.commit()

        response = label_audit_client.post(
            "/api/v2/labels/mark-event",
            headers={"Authorization": f"Bearer {token}"},
            json={"event_id": "duplicate_mark_event", "label_name": audit_label.label},
        )

        assert response.status_code == 200
        assert response.json()["event_version"] == 2
        assert session.query(EventVersionLabel).filter(EventVersionLabel.ev_id == latest_decision.ev_id).count() == 1
        assert session.query(LabelHistory).count() == 1

    def test_upload_rejects_invalid_file_type(self, label_audit_client):
        token = label_audit_client.test_data["token"]

        response = label_audit_client.post(
            "/api/v2/labels/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("labels.json", '{"event_id":"x"}', "application/json")},
        )

        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
