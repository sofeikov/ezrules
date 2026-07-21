"""Read-only operational case metrics for managers."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.operations import OperationsSummaryResponse
from ezrules.backend.operations_analytics import build_operations_summary
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import User

router = APIRouter(prefix="/api/v2/operations", tags=["Operations"])


@router.get("/summary", response_model=OperationsSummaryResponse)
def get_operations_summary(
    days: Literal[7, 30, 90] = Query(default=30, description="Calendar-day reporting window"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> OperationsSummaryResponse:
    """Return one bounded operational summary for the caller's organisation."""
    return OperationsSummaryResponse.model_validate(build_operations_summary(db, o_id=current_org_id, days=days))
