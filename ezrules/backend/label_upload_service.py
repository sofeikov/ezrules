import csv
import io
from dataclasses import dataclass, field

from ezrules.core.application_context import get_organization_id
from ezrules.models.backend_core import Label, TestingRecordLog


@dataclass
class AppliedLabelAssignment:
    """A successful label assignment applied from an upload row."""

    row_number: int
    event_id: str
    label_name: str
    label_id: int


@dataclass
class LabelUploadResult:
    """Result of a label upload operation"""

    success_count: int
    error_count: int
    errors: list[str]
    applied_assignments: list[AppliedLabelAssignment] = field(default_factory=list)


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

    def __init__(self, db_session, org_id: int | None = None):
        self.db_session = db_session
        self.org_id = org_id

    def _resolved_org_id(self) -> int:
        org_id = self.org_id if self.org_id is not None else get_organization_id()
        if org_id is None:
            raise RuntimeError("An organization context is required for label upload operations.")
        return org_id

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
        all_labels = self.db_session.query(Label).filter(Label.o_id == self._resolved_org_id()).all()
        return {str(label.label).upper(): label for label in all_labels}

    def process_label_assignments(
        self, parsed_rows: list[ParsedRow], label_cache: dict[str, Label]
    ) -> LabelUploadResult:
        """Process the actual label assignments to events"""
        success_count = 0
        error_count = 0
        errors: list[str] = []
        applied_assignments: list[AppliedLabelAssignment] = []

        for row in parsed_rows:
            try:
                org_id = self._resolved_org_id()
                # Find the event by event_id within the current organization.
                event_records = (
                    self.db_session.query(TestingRecordLog)
                    .filter(
                        TestingRecordLog.event_id == row.event_id,
                        TestingRecordLog.o_id == org_id,
                    )
                    .limit(2)
                    .all()
                )
                if not event_records:
                    error_count += 1
                    errors.append(f"Row {row.row_number}: Event with id '{row.event_id}' not found")
                    continue
                if len(event_records) > 1:
                    error_count += 1
                    errors.append(
                        f"Row {row.row_number}: Multiple events with id '{row.event_id}' found for the current organization"
                    )
                    continue
                event_record = event_records[0]

                # Find the label from cache
                label = label_cache.get(row.label_name)
                if not label:
                    error_count += 1
                    errors.append(f"Row {row.row_number}: Label '{row.label_name}' not found")
                    continue

                # Update the event record with the label
                event_record.el_id = label.el_id
                success_count += 1
                applied_assignments.append(
                    AppliedLabelAssignment(
                        row_number=row.row_number,
                        event_id=row.event_id,
                        label_name=row.label_name,
                        label_id=int(label.el_id),
                    )
                )

            except Exception as e:
                error_count += 1
                errors.append(f"Row {row.row_number}: Database error - {str(e)}")

        return LabelUploadResult(
            success_count=success_count,
            error_count=error_count,
            errors=errors,
            applied_assignments=applied_assignments,
        )

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
            success_count=result.success_count,
            error_count=result.error_count + len(format_errors),
            errors=all_errors,
            applied_assignments=result.applied_assignments,
        )
