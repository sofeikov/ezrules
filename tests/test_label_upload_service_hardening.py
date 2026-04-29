from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.models.backend_core import (
    EventVersionLabel,
    Label,
    Organisation,
)
from tests.canonical_helpers import add_served_decision


def test_upload_labels_from_csv_is_scoped_to_the_configured_org(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    other_org = Organisation(name="other_org")
    session.add(other_org)
    session.commit()

    label = Label(label="FRAUD")
    session.add(label)
    session.commit()
    add_served_decision(
        session,
        org_id=int(other_org.o_id),
        event_id="cross_org_event",
        event_timestamp=1234567890,
        event_data={"amount": 100},
    )

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv("cross_org_event,FRAUD\n")

    assert result.success_count == 0
    assert result.error_count == 1
    assert result.applied_assignments == []
    assert result.errors == ["Row 1: Served event with id 'cross_org_event' not found"]
    assert session.query(EventVersionLabel).count() == 0


def test_upload_labels_from_csv_labels_latest_duplicate_event_id_version(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    label = Label(label="NORMAL")
    session.add(label)
    session.commit()
    add_served_decision(
        session,
        org_id=int(current_org.o_id),
        event_id="duplicate_event",
        event_timestamp=1234567890,
        event_data={"amount": 100},
    )
    latest_decision = add_served_decision(
        session,
        org_id=int(current_org.o_id),
        event_id="duplicate_event",
        event_timestamp=1234567891,
        event_data={"amount": 200},
    )

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv("duplicate_event,NORMAL\n")

    assert result.success_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert result.applied_assignments[0].event_version == 2
    assignment = session.query(EventVersionLabel).one()
    assert assignment.ev_id == latest_decision.ev_id


def test_upload_labels_from_csv_returns_assignment_metadata_for_audit(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    label = Label(label="CHARGEBACK")
    session.add(label)
    session.commit()
    add_served_decision(
        session,
        org_id=int(current_org.o_id),
        event_id="audit_ready_event",
        event_timestamp=1234567890,
        event_data={"amount": 300},
    )

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv(
        "audit_ready_event,CHARGEBACK\n"
    )

    assert result.success_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert len(result.applied_assignments) == 1
    assert result.applied_assignments[0].row_number == 1
    assert result.applied_assignments[0].event_id == "audit_ready_event"
    assert result.applied_assignments[0].event_version == 1
    assert result.applied_assignments[0].label_name == "CHARGEBACK"
    assert result.applied_assignments[0].label_id == label.el_id
