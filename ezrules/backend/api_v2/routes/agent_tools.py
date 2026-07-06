from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.agent_tools import build_blast_radius, build_rule_counterexamples
from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.agent_tools import (
    RuleBlastRadiusRequest,
    RuleBlastRadiusResponse,
    RuleCounterexamplesRequest,
    RuleCounterexamplesResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import User

router = APIRouter(prefix="/api/v2/agent-tools", tags=["Agent Tools"])


def _validate_rule_logic(db: Any, org_id: int, logic: str) -> None:
    try:
        Rule(rid="", logic=logic, list_values_provider=PersistentUserListManager(db, org_id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid proposed rule logic: {exc!s}",
        ) from exc


@router.post("/rule-blast-radius", response_model=RuleBlastRadiusResponse)
def simulate_rule_blast_radius(
    request: RuleBlastRadiusRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleBlastRadiusResponse:
    _validate_rule_logic(db, current_org_id, request.proposed_logic)
    payload = build_blast_radius(
        db,
        org_id=current_org_id,
        rule_id=request.rule_id,
        proposed_logic=request.proposed_logic,
        lookback_days=request.lookback_days,
        group_by=request.group_by,
        sample_limit=request.sample_limit,
        max_records=request.max_records,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return RuleBlastRadiusResponse.model_validate(payload)


@router.post("/rule-counterexamples", response_model=RuleCounterexamplesResponse)
def find_rule_counterexamples(
    request: RuleCounterexamplesRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    __: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleCounterexamplesResponse:
    if request.proposed_logic is not None:
        _validate_rule_logic(db, current_org_id, request.proposed_logic)
    payload = build_rule_counterexamples(
        db,
        org_id=current_org_id,
        rule_id=request.rule_id,
        proposed_logic=request.proposed_logic,
        lookback_days=request.lookback_days,
        positive_labels=request.positive_labels,
        negative_labels=request.negative_labels,
        target_outcomes=request.target_outcomes,
        sample_limit=request.sample_limit,
        max_records=request.max_records,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return RuleCounterexamplesResponse.model_validate(payload)
