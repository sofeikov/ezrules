from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.models.backend_core import Label, Organisation, TestingRecordLog


def test_upload_labels_from_csv_is_scoped_to_the_configured_org(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    other_org = Organisation(name="other_org")
    session.add(other_org)
    session.commit()

    label = Label(label="FRAUD")
    off_scope_event = TestingRecordLog(
        event_id="cross_org_event",
        event_timestamp=1234567890,
        event={"amount": 100},
        o_id=other_org.o_id,
    )
    session.add(label)
    session.add(off_scope_event)
    session.commit()

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv("cross_org_event,FRAUD\n")

    assert result.success_count == 0
    assert result.error_count == 1
    assert result.applied_assignments == []
    assert result.errors == ["Row 1: Event with id 'cross_org_event' not found"]

    session.refresh(off_scope_event)
    assert off_scope_event.el_id is None


def test_upload_labels_from_csv_rejects_duplicate_event_ids_in_org(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    label = Label(label="NORMAL")
    first_event = TestingRecordLog(
        event_id="duplicate_event",
        event_timestamp=1234567890,
        event={"amount": 100},
        o_id=current_org.o_id,
    )
    second_event = TestingRecordLog(
        event_id="duplicate_event",
        event_timestamp=1234567891,
        event={"amount": 200},
        o_id=current_org.o_id,
    )
    session.add(label)
    session.add(first_event)
    session.add(second_event)
    session.commit()

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv("duplicate_event,NORMAL\n")

    assert result.success_count == 0
    assert result.error_count == 1
    assert result.applied_assignments == []
    assert result.errors == ["Row 1: Multiple events with id 'duplicate_event' found for the current organization"]

    session.refresh(first_event)
    session.refresh(second_event)
    assert first_event.el_id is None
    assert second_event.el_id is None


def test_upload_labels_from_csv_returns_assignment_metadata_for_audit(session):
    current_org = session.query(Organisation).first()
    assert current_org is not None

    label = Label(label="CHARGEBACK")
    event = TestingRecordLog(
        event_id="audit_ready_event",
        event_timestamp=1234567890,
        event={"amount": 300},
        o_id=current_org.o_id,
    )
    session.add(label)
    session.add(event)
    session.commit()

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv(
        "audit_ready_event,CHARGEBACK\n"
    )

    assert result.success_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert len(result.applied_assignments) == 1
    assert result.applied_assignments[0].row_number == 1
    assert result.applied_assignments[0].event_id == "audit_ready_event"
    assert result.applied_assignments[0].label_name == "CHARGEBACK"
    assert result.applied_assignments[0].label_id == label.el_id
