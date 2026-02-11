"""
FastAPI routes for outcome management.

These endpoints provide CRUD operations for allowed outcomes.
All endpoints require authentication and appropriate permissions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.outcomes import (
    OutcomeCreate,
    OutcomeListItem,
    OutcomeMutationResponse,
    OutcomeResponse,
    OutcomesListResponse,
)
from ezrules.core.audit_helpers import save_outcome_history
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AllowedOutcome, User

router = APIRouter(prefix="/api/v2/outcomes", tags=["Outcomes"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_outcome_manager(db: Any) -> DatabaseOutcome:
    """Get an outcome manager instance for the current organization."""
    # For now, use o_id=1 as default. In multi-tenant setup, this would come from user context.
    o_id = 1
    return DatabaseOutcome(db_session=db, o_id=o_id)


def outcome_to_response(outcome: AllowedOutcome) -> OutcomeResponse:
    """Convert a database outcome model to API response."""
    return OutcomeResponse(
        ao_id=int(outcome.ao_id),
        outcome_name=str(outcome.outcome_name),
        created_at=outcome.created_at,  # type: ignore[arg-type]
    )


# =============================================================================
# LIST OUTCOMES
# =============================================================================


@router.get("", response_model=OutcomesListResponse)
def list_outcomes(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_OUTCOMES)),
    db: Any = Depends(get_db),
) -> OutcomesListResponse:
    """
    Get all allowed outcomes.

    Returns a list of all outcomes that rules can return.
    """
    o_id = 1  # Default org ID
    outcomes = db.query(AllowedOutcome).filter(AllowedOutcome.o_id == o_id).all()

    outcomes_data = [
        OutcomeListItem(
            ao_id=int(outcome.ao_id),
            outcome_name=str(outcome.outcome_name),
            created_at=outcome.created_at,  # type: ignore[arg-type]
        )
        for outcome in outcomes
    ]

    return OutcomesListResponse(outcomes=outcomes_data)


# =============================================================================
# CREATE OUTCOME
# =============================================================================


@router.post("", response_model=OutcomeMutationResponse, status_code=status.HTTP_201_CREATED)
def create_outcome(
    outcome_data: OutcomeCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_OUTCOME)),
    db: Any = Depends(get_db),
) -> OutcomeMutationResponse:
    """
    Create a new allowed outcome.

    The outcome name will be converted to uppercase.
    Returns an error if the outcome already exists.
    """
    outcome_manager = get_outcome_manager(db)
    outcome_name = outcome_data.outcome_name.strip().upper()

    # Check if outcome already exists
    if outcome_manager.is_allowed_outcome(outcome_name):
        return OutcomeMutationResponse(
            success=False,
            message="Outcome already exists",
            error=f"Outcome '{outcome_name}' already exists",
        )

    # Create the outcome
    outcome_manager.add_outcome(outcome_name)

    # Fetch the newly created outcome for the response
    o_id = 1
    new_outcome = (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.outcome_name == outcome_name, AllowedOutcome.o_id == o_id)
        .first()
    )

    if new_outcome:
        save_outcome_history(
            db,
            ao_id=new_outcome.ao_id,
            outcome_name=outcome_name,
            action="created",
            o_id=o_id,
            changed_by=str(user.email) if user.email else None,
        )
        db.commit()

    return OutcomeMutationResponse(
        success=True,
        message="Outcome created successfully",
        outcome=outcome_to_response(new_outcome) if new_outcome else None,
    )


# =============================================================================
# DELETE OUTCOME
# =============================================================================


@router.delete("/{outcome_name}", response_model=OutcomeMutationResponse)
def delete_outcome(
    outcome_name: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_OUTCOME)),
    db: Any = Depends(get_db),
) -> OutcomeMutationResponse:
    """
    Delete an allowed outcome.

    Returns 404 if the outcome doesn't exist.
    """
    outcome_manager = get_outcome_manager(db)
    outcome_name = outcome_name.strip().upper()

    # Check if outcome exists
    if not outcome_manager.is_allowed_outcome(outcome_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outcome '{outcome_name}' not found",
        )

    # Get outcome ID before deletion
    o_id = 1
    outcome_obj = (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.outcome_name == outcome_name, AllowedOutcome.o_id == o_id)
        .first()
    )
    ao_id = outcome_obj.ao_id if outcome_obj else 0

    save_outcome_history(
        db,
        ao_id=ao_id,
        outcome_name=outcome_name,
        action="deleted",
        o_id=o_id,
        changed_by=str(user.email) if user.email else None,
    )

    # Delete the outcome
    outcome_manager.remove_outcome(outcome_name)

    return OutcomeMutationResponse(
        success=True,
        message=f"Outcome '{outcome_name}' deleted successfully",
    )
