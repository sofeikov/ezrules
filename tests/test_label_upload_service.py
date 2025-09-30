"""Tests for the LabelUploadService"""

import pytest
from ezrules.backend.label_upload_service import LabelUploadService, ParsedRow
from ezrules.models.backend_core import Label, TestingRecordLog, Organisation


class TestLabelUploadService:
    """Test the LabelUploadService class"""

    def test_parse_csv_content_valid(self):
        """Test parsing valid CSV content"""
        service = LabelUploadService(None)  # No DB session needed for parsing
        csv_content = "event_123,FRAUD\nevent_456,NORMAL\n"

        parsed_rows, format_errors = service.parse_csv_content(csv_content)

        assert len(parsed_rows) == 2
        assert len(format_errors) == 0

        assert parsed_rows[0].event_id == "event_123"
        assert parsed_rows[0].label_name == "FRAUD"
        assert parsed_rows[0].row_number == 1
        assert parsed_rows[0].is_valid is True

        assert parsed_rows[1].event_id == "event_456"
        assert parsed_rows[1].label_name == "NORMAL"
        assert parsed_rows[1].row_number == 2

    def test_parse_csv_content_invalid_columns(self):
        """Test parsing CSV with wrong number of columns"""
        service = LabelUploadService(None)
        csv_content = "event_only\nevent_id,label,extra\n"

        parsed_rows, format_errors = service.parse_csv_content(csv_content)

        assert len(parsed_rows) == 0
        assert len(format_errors) == 2
        assert "Expected 2 columns" in format_errors[0]
        assert "Expected 2 columns" in format_errors[1]

    def test_parse_csv_content_empty_values(self):
        """Test parsing CSV with empty values"""
        service = LabelUploadService(None)
        csv_content = ",FRAUD\nevent_123,\n  ,  \n"

        parsed_rows, format_errors = service.parse_csv_content(csv_content)

        assert len(parsed_rows) == 0
        assert len(format_errors) == 3
        assert all("Empty event_id or label_name" in error for error in format_errors)

    def test_parse_csv_content_whitespace_handling(self):
        """Test that whitespace is properly trimmed and labels are uppercased"""
        service = LabelUploadService(None)
        csv_content = "  event_123  ,  fraud  \n"

        parsed_rows, format_errors = service.parse_csv_content(csv_content)

        assert len(parsed_rows) == 1
        assert len(format_errors) == 0
        assert parsed_rows[0].event_id == "event_123"
        assert parsed_rows[0].label_name == "FRAUD"

    def test_get_label_cache(self, session):
        """Test getting label cache from database"""
        # Create test labels
        fraud_label = Label(label="FRAUD")
        normal_label = Label(label="NORMAL")
        session.add(fraud_label)
        session.add(normal_label)
        session.commit()

        service = LabelUploadService(session)
        label_cache = service.get_label_cache()

        assert len(label_cache) >= 2  # May include default labels
        assert "FRAUD" in label_cache
        assert "NORMAL" in label_cache
        assert label_cache["FRAUD"].label == "FRAUD"
        assert label_cache["NORMAL"].label == "NORMAL"

    def test_process_label_assignments_success(self, session):
        """Test successful label assignments"""
        # Create test data
        org = session.query(Organisation).first()
        test_event = TestingRecordLog(
            event_id="test_event", event_timestamp=1234567890, event={"test": "data"}, o_id=org.o_id
        )
        fraud_label = Label(label="FRAUD")
        session.add(test_event)
        session.add(fraud_label)
        session.commit()

        # Create service and test data
        service = LabelUploadService(session)
        parsed_rows = [ParsedRow(row_number=1, event_id="test_event", label_name="FRAUD", is_valid=True)]
        label_cache = {"FRAUD": fraud_label}

        result = service.process_label_assignments(parsed_rows, label_cache)

        assert result.success_count == 1
        assert result.error_count == 0
        assert len(result.errors) == 0

        # The service doesn't commit, that's the controller's responsibility
        # But we can verify the assignment was made in memory
        assert test_event.el_id == fraud_label.el_id

    def test_process_label_assignments_event_not_found(self, session):
        """Test handling of non-existent events"""
        fraud_label = Label(label="FRAUD")
        session.add(fraud_label)
        session.commit()

        service = LabelUploadService(session)
        parsed_rows = [ParsedRow(row_number=1, event_id="nonexistent_event", label_name="FRAUD", is_valid=True)]
        label_cache = {"FRAUD": fraud_label}

        result = service.process_label_assignments(parsed_rows, label_cache)

        assert result.success_count == 0
        assert result.error_count == 1
        assert "Event with id 'nonexistent_event' not found" in result.errors[0]

    def test_process_label_assignments_label_not_found(self, session):
        """Test handling of non-existent labels"""
        org = session.query(Organisation).first()
        test_event = TestingRecordLog(
            event_id="test_event", event_timestamp=1234567890, event={"test": "data"}, o_id=org.o_id
        )
        session.add(test_event)
        session.commit()

        service = LabelUploadService(session)
        parsed_rows = [ParsedRow(row_number=1, event_id="test_event", label_name="NONEXISTENT_LABEL", is_valid=True)]
        label_cache = {}  # Empty cache

        result = service.process_label_assignments(parsed_rows, label_cache)

        assert result.success_count == 0
        assert result.error_count == 1
        assert "Label 'NONEXISTENT_LABEL' not found" in result.errors[0]

    def test_upload_labels_from_csv_complete_workflow(self, session):
        """Test the complete workflow from CSV to database"""
        # Create test data
        org = session.query(Organisation).first()
        test_event1 = TestingRecordLog(
            event_id="event_1", event_timestamp=1234567890, event={"test": "data1"}, o_id=org.o_id
        )
        test_event2 = TestingRecordLog(
            event_id="event_2", event_timestamp=1234567891, event={"test": "data2"}, o_id=org.o_id
        )
        fraud_label = Label(label="FRAUD")
        normal_label = Label(label="NORMAL")
        session.add(test_event1)
        session.add(test_event2)
        session.add(fraud_label)
        session.add(normal_label)
        session.commit()

        # Test the complete workflow
        service = LabelUploadService(session)
        csv_content = "event_1,FRAUD\nevent_2,NORMAL\ninvalid_event,FRAUD\n"

        result = service.upload_labels_from_csv(csv_content)

        assert result.success_count == 2
        assert result.error_count == 1
        assert len(result.errors) == 1
        assert "Event with id 'invalid_event' not found" in result.errors[0]

        # Verify database updates
        session.refresh(test_event1)
        session.refresh(test_event2)
        assert test_event1.el_id == fraud_label.el_id
        assert test_event2.el_id == normal_label.el_id

    def test_upload_labels_from_csv_empty_content(self, session):
        """Test handling of empty CSV content"""
        service = LabelUploadService(session)
        csv_content = ""

        result = service.upload_labels_from_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 0
        assert len(result.errors) == 0
