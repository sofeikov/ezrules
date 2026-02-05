"""
FastAPI routes for label management.

These endpoints provide CRUD operations for event labels and marking events.
All endpoints require authentication and appropriate permissions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
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
)
from ezrules.core.labels import DatabaseLabelManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, TestingRecordLog, User

router = APIRouter(prefix="/api/v2/labels", tags=["Labels"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_label_manager(db: Any) -> DatabaseLabelManager:
    """Get a label manager instance for the current organization."""
    # For now, use o_id=1 as default. In multi-tenant setup, this would come from user context.
    o_id = 1
    return DatabaseLabelManager(db_session=db, o_id=o_id)


def label_to_response(label: Label) -> LabelResponse:
    """Convert a database label model to API response."""
    return LabelResponse(
        el_id=int(label.el_id),
        label=str(label.label),
    )


# =============================================================================
# LIST LABELS
# =============================================================================


@router.get("", response_model=LabelsListResponse)
def list_labels(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    db: Any = Depends(get_db),
) -> LabelsListResponse:
    """
    Get all labels.

    Returns a list of all labels that can be applied to events.
    """
    labels = db.query(Label).all()

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
    db: Any = Depends(get_db),
) -> LabelMutationResponse:
    """
    Create a new label.

    The label name will be converted to uppercase.
    Returns an error if the label already exists.
    """
    label_manager = get_label_manager(db)
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
    new_label = db.query(Label).filter(Label.label == label_name).first()

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
    db: Any = Depends(get_db),
) -> LabelBulkCreateResponse:
    """
    Create multiple labels at once.

    Label names will be converted to uppercase.
    Returns lists of successfully created and failed labels.
    """
    label_manager = get_label_manager(db)
    created = []
    failed = []

    for label_name in bulk_data.labels:
        label_name = label_name.strip().upper()
        if label_manager.label_exists(label_name):
            failed.append(label_name)
        else:
            label_manager.add_label(label_name)
            created.append(label_name)

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
    db: Any = Depends(get_db),
) -> LabelMutationResponse:
    """
    Delete a label.

    Returns 404 if the label doesn't exist.
    """
    label_manager = get_label_manager(db)
    label_name = label_name.strip().upper()

    # Check if label exists
    if not label_manager.label_exists(label_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_name}' not found",
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
    db: Any = Depends(get_db),
) -> MarkEventResponse:
    """
    Mark an event with a label for analytics purposes.

    Associates an existing event with an existing label.
    """
    event_id = request_data.event_id
    label_name = request_data.label_name.strip().upper()

    # Find the event by event_id
    event_record = db.query(TestingRecordLog).filter_by(event_id=event_id).first()
    if not event_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with id '{event_id}' not found",
        )

    # Find the label by name
    label = db.query(Label).filter_by(label=label_name).first()
    if not label:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_name}' not found",
        )

    # Update the event record with the label
    event_record.el_id = label.el_id
    db.commit()

    return MarkEventResponse(
        success=True,
        message=f"Event '{event_id}' successfully marked with label '{label_name}'",
        event_id=event_id,
        label_name=label_name,
    )
