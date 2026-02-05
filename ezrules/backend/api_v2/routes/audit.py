"""
FastAPI routes for audit trail.

These endpoints provide access to the version history of rules and configurations.
All endpoints require authentication and ACCESS_AUDIT_TRAIL permission.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.audit import (
    AuditSummaryResponse,
    ConfigAuditListResponse,
    RuleAuditResponse,
    RuleEngineConfigHistoryEntry,
    RuleHistoryEntry,
    RulesAuditListResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Rule,
    RuleEngineConfigHistory,
    RuleHistory,
    User,
)

router = APIRouter(prefix="/api/v2/audit", tags=["Audit Trail"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def rule_history_to_response(history: RuleHistory) -> RuleHistoryEntry:
    """Convert a rule history record to API response."""
    changed = history.changed if history.changed is not None else None

    return RuleHistoryEntry(
        r_id=int(history.r_id),
        rid=str(history.rid),
        version=int(history.version),
        logic=str(history.logic),
        description=str(history.description),
        changed=changed,  # type: ignore[arg-type]
    )


def config_history_to_response(history: RuleEngineConfigHistory) -> RuleEngineConfigHistoryEntry:
    """Convert a config history record to API response."""
    changed = history.changed if history.changed is not None else None

    return RuleEngineConfigHistoryEntry(
        re_id=int(history.re_id),
        label=str(history.label),
        version=int(history.version),
        config=dict(history.config) if history.config else {},
        changed=changed,  # type: ignore[arg-type]
    )


# =============================================================================
# AUDIT SUMMARY
# =============================================================================


@router.get("", response_model=AuditSummaryResponse)
def get_audit_summary(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
) -> AuditSummaryResponse:
    """
    Get a summary of audit trail data.

    Returns counts of version history entries.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    total_rule_versions = db.query(RuleHistory).count()
    total_config_versions = db.query(RuleEngineConfigHistory).count()

    # Count distinct rules/configs with history
    rules_with_changes = db.query(RuleHistory.r_id).distinct().count()
    configs_with_changes = db.query(RuleEngineConfigHistory.re_id).distinct().count()

    return AuditSummaryResponse(
        total_rule_versions=total_rule_versions,
        total_config_versions=total_config_versions,
        rules_with_changes=rules_with_changes,
        configs_with_changes=configs_with_changes,
    )


# =============================================================================
# RULE HISTORY
# =============================================================================


@router.get("/rules", response_model=RulesAuditListResponse)
def list_rule_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    rule_id: int | None = Query(default=None, description="Filter by rule ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> RulesAuditListResponse:
    """
    Get paginated rule version history.

    Returns all rule changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(RuleHistory)

    # Apply filters
    if start_date:
        query = query.filter(RuleHistory.changed >= start_date)
    if end_date:
        query = query.filter(RuleHistory.changed <= end_date)
    if rule_id:
        query = query.filter(RuleHistory.r_id == rule_id)

    # Get total count before pagination
    total = query.count()

    # Apply ordering and pagination
    items = query.order_by(RuleHistory.changed.desc()).offset(offset).limit(limit).all()

    return RulesAuditListResponse(
        total=total,
        items=[rule_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


@router.get("/rules/{rule_id}", response_model=RuleAuditResponse)
def get_rule_audit(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
) -> RuleAuditResponse:
    """
    Get complete version history for a specific rule.

    Returns all versions of the rule from oldest to newest.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    # Get the current rule
    rule = db.query(Rule).filter(Rule.r_id == rule_id).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with id {rule_id} not found",
        )

    # Get all history entries for this rule
    history = db.query(RuleHistory).filter(RuleHistory.r_id == rule_id).order_by(RuleHistory.version.asc()).all()

    return RuleAuditResponse(
        r_id=int(rule.r_id),
        rid=str(rule.rid),
        current_version=int(rule.version),
        history=[rule_history_to_response(h) for h in history],
    )


# =============================================================================
# CONFIG HISTORY
# =============================================================================


@router.get("/config", response_model=ConfigAuditListResponse)
def list_config_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    config_id: int | None = Query(default=None, description="Filter by config ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> ConfigAuditListResponse:
    """
    Get paginated config version history.

    Returns all config changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(RuleEngineConfigHistory)

    # Apply filters
    if start_date:
        query = query.filter(RuleEngineConfigHistory.changed >= start_date)
    if end_date:
        query = query.filter(RuleEngineConfigHistory.changed <= end_date)
    if config_id:
        query = query.filter(RuleEngineConfigHistory.re_id == config_id)

    # Get total count before pagination
    total = query.count()

    # Apply ordering and pagination
    items = query.order_by(RuleEngineConfigHistory.changed.desc()).offset(offset).limit(limit).all()

    return ConfigAuditListResponse(
        total=total,
        items=[config_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )
