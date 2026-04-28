from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.models.backend_core import (
    EvaluationDecision,
    EventVersion,
    EventVersionLabel,
    Label,
    Organisation,
    TestingRecordLog,
)


def _add_served_event_version(session, event: TestingRecordLog, event_version: int = 1) -> EventVersion:
    version = EventVersion(
        o_id=event.o_id,
        event_id=event.event_id,
        event_version=event_version,
        event_timestamp=event.event_timestamp,
        event_data=event.event,
        payload_hash="0" * 64,
        source="evaluate",
    )
    session.add(version)
    session.flush()
    session.add(
        EvaluationDecision(
            ev_id=version.ev_id,
            tl_id=event.tl_id,
            o_id=event.o_id,
            event_id=event.event_id,
            event_version=event_version,
            event_timestamp=event.event_timestamp,
            decision_type="served",
            served=True,
            rule_config_label="production",
        )
    )
    session.commit()
    return version


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
    assert result.errors == ["Row 1: Served event with id 'cross_org_event' not found"]
    assert session.query(EventVersionLabel).count() == 0


def test_upload_labels_from_csv_labels_latest_duplicate_event_id_version(session):
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
    _add_served_event_version(session, first_event, event_version=1)
    latest_version = _add_served_event_version(session, second_event, event_version=2)

    result = LabelUploadService(session, org_id=current_org.o_id).upload_labels_from_csv("duplicate_event,NORMAL\n")

    assert result.success_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert result.applied_assignments[0].event_version == 2
    assignment = session.query(EventVersionLabel).one()
    assert assignment.ev_id == latest_version.ev_id


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
    _add_served_event_version(session, event)

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
