"""
FastAPI routes for label management.

These endpoints provide CRUD operations for event labels and marking events.
All endpoints require authentication and appropriate permissions.
"""

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.labels import (
    LabelBulkCreate,
    LabelBulkCreateResponse,
    LabelCreate,
    LabelListItem,
    LabelMutationResponse,
    LabelResponse,
    LabelsListResponse,
    MarkEventRequest,
    MarkEventResponse,
    UploadResult,
    UploadResultError,
)
from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.core.audit_helpers import save_label_history
from ezrules.core.labels import DatabaseLabelManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, TestingRecordLog, User

router = APIRouter(prefix="/api/v2/labels", tags=["Labels"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_label_manager(db: Any, org_id: int) -> DatabaseLabelManager:
    """Get a label manager instance for the current organization."""
    return DatabaseLabelManager(db_session=db, o_id=org_id)


def get_unique_event_for_labeling(db: Any, event_id: str, org_id: int) -> TestingRecordLog:
    """Load a single event in the active organization or raise a precise error."""
    matches = (
        db.query(TestingRecordLog)
        .filter(
            TestingRecordLog.event_id == event_id,
            TestingRecordLog.o_id == org_id,
        )
        .limit(2)
        .all()
    )

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with id '{event_id}' not found",
        )
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Multiple events with id '{event_id}' found for the current organization",
        )

    return matches[0]


def label_to_response(label: Label) -> LabelResponse:
    """Convert a database label model to API response."""
    return LabelResponse(
        el_id=int(label.el_id),
        label=str(label.label),
    )


def get_label_by_name(db: Any, label_name: str, org_id: int) -> Label | None:
    """Load a label by name within the active organization using case-insensitive matching."""
    return (
        db.query(Label)
        .filter(
            Label.o_id == org_id,
            func.upper(Label.label) == label_name.strip().upper(),
        )
        .first()
    )


# =============================================================================
# LIST LABELS
# =============================================================================


@router.get("", response_model=LabelsListResponse)
def list_labels(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> LabelsListResponse:
    """
    Get all labels.

    Returns a list of all labels that can be applied to events.
    """
    labels = db.query(Label).filter(Label.o_id == current_org_id).all()

    labels_data = [
        LabelListItem(
            el_id=int(label.el_id),
            label=str(label.label),
        )
        for label in labels
    ]

    return LabelsListResponse(labels=labels_data)


# =============================================================================
# CREATE LABEL
# =============================================================================


@router.post("", response_model=LabelMutationResponse, status_code=status.HTTP_201_CREATED)
def create_label(
    label_data: LabelCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_LABEL)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> LabelMutationResponse:
    """
    Create a new label.

    The label name will be converted to uppercase.
    Returns an error if the label already exists.
    """
    label_manager = get_label_manager(db, current_org_id)
    label_name = label_data.label_name.strip().upper()

    # Check if label already exists
    if label_manager.label_exists(label_name):
        return LabelMutationResponse(
            success=False,
            message="Label already exists",
            error=f"Label '{label_name}' already exists",
        )

    # Create the label
    label_manager.add_label(label_name)

    # Fetch the newly created label for the response
    new_label = get_label_by_name(db, label_name, current_org_id)

    if new_label:
        save_label_history(
            db,
            el_id=int(new_label.el_id),
            label=label_name,
            action="created",
            o_id=current_org_id,
            changed_by=str(user.email) if user.email else None,
        )
        db.commit()

    return LabelMutationResponse(
        success=True,
        message="Label created successfully",
        label=label_to_response(new_label) if new_label else None,
    )


# =============================================================================
# BULK CREATE LABELS
# =============================================================================


@router.post("/bulk", response_model=LabelBulkCreateResponse, status_code=status.HTTP_201_CREATED)
def create_labels_bulk(
    bulk_data: LabelBulkCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_LABEL)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> LabelBulkCreateResponse:
    """
    Create multiple labels at once.

    Label names will be converted to uppercase.
    Returns lists of successfully created and failed labels.
    """
    label_manager = get_label_manager(db, current_org_id)
    created = []
    failed = []

    for label_name in bulk_data.labels:
        label_name = label_name.strip().upper()
        if label_manager.label_exists(label_name):
            failed.append(label_name)
        else:
            label_manager.add_label(label_name)
            created.append(label_name)

    # Record audit entries for each created label
    for label_name in created:
        label_obj = get_label_by_name(db, label_name, current_org_id)
        if label_obj:
            save_label_history(
                db,
                el_id=int(label_obj.el_id),
                label=label_name,
                action="created",
                o_id=current_org_id,
                changed_by=str(user.email) if user.email else None,
            )
    if created:
        db.commit()

    return LabelBulkCreateResponse(
        success=len(failed) == 0,
        message=f"Created {len(created)} labels, {len(failed)} failed",
        created=created,
        failed=failed,
    )


# =============================================================================
# DELETE LABEL
# =============================================================================


@router.delete("/{label_name}", response_model=LabelMutationResponse)
def delete_label(
    label_name: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_LABEL)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> LabelMutationResponse:
    """
    Delete a label.

    Returns 404 if the label doesn't exist.
    """
    label_manager = get_label_manager(db, current_org_id)
    label_name = label_name.strip().upper()

    # Check if label exists
    if not label_manager.label_exists(label_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_name}' not found",
        )

    # Get label ID before deletion
    label_obj = get_label_by_name(db, label_name, current_org_id)
    el_id = int(label_obj.el_id) if label_obj else 0

    save_label_history(
        db,
        el_id=el_id,
        label=label_name,
        action="deleted",
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
    )

    # Delete the label
    label_manager.remove_label(label_name)

    return LabelMutationResponse(
        success=True,
        message=f"Label '{label_name}' deleted successfully",
    )


# =============================================================================
# MARK EVENT
# =============================================================================


@router.post("/mark-event", response_model=MarkEventResponse)
def mark_event(
    request_data: MarkEventRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_LABEL)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> MarkEventResponse:
    """
    Mark an event with a label for analytics purposes.

    Associates an existing event with an existing label.
    """
    event_id = request_data.event_id
    label_name = request_data.label_name.strip().upper()

    event_record = get_unique_event_for_labeling(db, event_id, current_org_id)

    # Find the label by name
    label = get_label_by_name(db, label_name, current_org_id)
    if not label:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_name}' not found",
        )

    # Update the event record with the label
    event_record.el_id = label.el_id
    save_label_history(
        db,
        el_id=int(label.el_id),
        label=label_name,
        action="assigned",
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
        details=f"Event ID: {event_id}",
    )
    db.commit()

    return MarkEventResponse(
        success=True,
        message=f"Event '{event_id}' successfully marked with label '{label_name}'",
        event_id=event_id,
        label_name=label_name,
    )


# =============================================================================
# CSV UPLOAD
# =============================================================================

ROW_NUMBER_PATTERN = re.compile(r"^Row (\d+): (.+)$")


def _parse_row_error(error_str: str) -> UploadResultError:
    """Parse an error string from LabelUploadService into an UploadResultError."""
    match = ROW_NUMBER_PATTERN.match(error_str)
    if match:
        return UploadResultError(row=int(match.group(1)), error=match.group(2))
    return UploadResultError(row=0, error=error_str)


@router.post("/upload", response_model=UploadResult)
async def upload_labels(
    file: UploadFile,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_LABEL)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> UploadResult:
    """
    Upload a CSV file to bulk-assign labels to events.

    CSV format: event_id,label_name (one per line, no header row).
    """
    if file.content_type not in ("text/csv", "application/octet-stream", "text/plain"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{file.content_type}'. Expected a CSV file.",
        )

    raw_bytes = await file.read()
    try:
        csv_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not valid UTF-8 encoded text.",
        ) from err

    service = LabelUploadService(db, org_id=current_org_id)
    result = service.upload_labels_from_csv(csv_content)

    for assignment in result.applied_assignments:
        save_label_history(
            db,
            el_id=assignment.label_id,
            label=assignment.label_name,
            action="assigned_via_csv",
            o_id=current_org_id,
            changed_by=str(user.email) if user.email else None,
            details=f"Event ID: {assignment.event_id}",
        )

    db.commit()

    total_rows = result.success_count + result.error_count
    errors = [_parse_row_error(e) for e in result.errors]

    return UploadResult(
        total_rows=total_rows,
        successful=result.success_count,
        failed=result.error_count,
        errors=errors,
    )
