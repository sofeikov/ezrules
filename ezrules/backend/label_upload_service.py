import csv
import io
from dataclasses import dataclass

from ezrules.models.backend_core import Label, TestingRecordLog


@dataclass
class LabelUploadResult:
    """Result of a label upload operation"""

    success_count: int
    error_count: int
    errors: list[str]


@dataclass
class ParsedRow:
    """A parsed CSV row with validation status"""

    row_number: int
    event_id: str
    label_name: str
    is_valid: bool
    error_message: str = ""


class LabelUploadService:
    """Service for handling CSV label upload operations"""

    def __init__(self, db_session):
        self.db_session = db_session

    def parse_csv_content(self, csv_content: str) -> tuple[list[ParsedRow], list[str]]:
        """Parse CSV content and validate format"""
        stream = io.StringIO(csv_content)
        csv_reader = csv.reader(stream)

        parsed_rows = []
        format_errors = []

        for row_num, row in enumerate(csv_reader, 1):
            if len(row) != 2:
                format_errors.append(f"Row {row_num}: Expected 2 columns (event_id,label), got {len(row)}")
                continue

            event_id, label_name = row
            event_id = event_id.strip()
            label_name = label_name.strip().upper()

            if not event_id or not label_name:
                format_errors.append(f"Row {row_num}: Empty event_id or label_name")
                continue

            parsed_rows.append(ParsedRow(row_number=row_num, event_id=event_id, label_name=label_name, is_valid=True))

        return parsed_rows, format_errors

    def get_label_cache(self) -> dict[str, Label]:
        """Get a dictionary mapping label names to Label objects"""
        all_labels = self.db_session.query(Label).all()
        return {label.label: label for label in all_labels}

    def process_label_assignments(
        self, parsed_rows: list[ParsedRow], label_cache: dict[str, Label]
    ) -> LabelUploadResult:
        """Process the actual label assignments to events"""
        success_count = 0
        error_count = 0
        errors = []

        for row in parsed_rows:
            try:
                # Find the event by event_id
                event_record = self.db_session.query(TestingRecordLog).filter_by(event_id=row.event_id).first()
                if not event_record:
                    error_count += 1
                    errors.append(f"Row {row.row_number}: Event with id '{row.event_id}' not found")
                    continue

                # Find the label from cache
                label = label_cache.get(row.label_name)
                if not label:
                    error_count += 1
                    errors.append(f"Row {row.row_number}: Label '{row.label_name}' not found")
                    continue

                # Update the event record with the label
                event_record.el_id = label.el_id
                success_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"Row {row.row_number}: Database error - {str(e)}")

        return LabelUploadResult(success_count=success_count, error_count=error_count, errors=errors)

    def upload_labels_from_csv(self, csv_content: str) -> LabelUploadResult:
        """Complete workflow for uploading labels from CSV content"""
        # Step 1: Parse and validate CSV format
        parsed_rows, format_errors = self.parse_csv_content(csv_content)

        if not parsed_rows and format_errors:
            return LabelUploadResult(success_count=0, error_count=len(format_errors), errors=format_errors)

        # Step 2: Get label cache
        label_cache = self.get_label_cache()

        # Step 3: Process assignments
        result = self.process_label_assignments(parsed_rows, label_cache)

        # Combine format errors with processing errors
        all_errors = format_errors + result.errors

        return LabelUploadResult(
            success_count=result.success_count, error_count=result.error_count + len(format_errors), errors=all_errors
        )
