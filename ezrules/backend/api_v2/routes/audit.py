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
    FieldTypeAuditListResponse,
    FieldTypeHistoryEntry,
    LabelAuditListResponse,
    LabelHistoryEntry,
    OutcomeAuditListResponse,
    OutcomeHistoryEntry,
    RolePermissionAuditListResponse,
    RolePermissionHistoryEntry,
    RuleAuditResponse,
    RuleEngineConfigHistoryEntry,
    RuleHistoryEntry,
    RulesAuditListResponse,
    UserAccountAuditListResponse,
    UserAccountHistoryEntry,
    UserListAuditListResponse,
    UserListHistoryEntry,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    FieldTypeHistory,
    LabelHistory,
    OutcomeHistory,
    RolePermissionHistory,
    Rule,
    RuleEngineConfigHistory,
    RuleHistory,
    User,
    UserAccountHistory,
    UserListHistory,
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
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def user_list_history_to_response(history: UserListHistory) -> UserListHistoryEntry:
    """Convert a user list history record to API response."""
    return UserListHistoryEntry(
        id=int(history.id),
        ul_id=int(history.ul_id),
        list_name=str(history.list_name),
        action=str(history.action),
        details=str(history.details) if history.details else None,
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def outcome_history_to_response(history: OutcomeHistory) -> OutcomeHistoryEntry:
    """Convert an outcome history record to API response."""
    return OutcomeHistoryEntry(
        id=int(history.id),
        ao_id=int(history.ao_id),
        outcome_name=str(history.outcome_name),
        action=str(history.action),
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def label_history_to_response(history: LabelHistory) -> LabelHistoryEntry:
    """Convert a label history record to API response."""
    return LabelHistoryEntry(
        id=int(history.id),
        el_id=int(history.el_id),
        label=str(history.label),
        action=str(history.action),
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def user_account_history_to_response(history: UserAccountHistory) -> UserAccountHistoryEntry:
    """Convert a user account history record to API response."""
    return UserAccountHistoryEntry(
        id=int(history.id),
        user_id=int(history.user_id),
        user_email=str(history.user_email),
        action=str(history.action),
        details=str(history.details) if history.details else None,
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def config_history_to_response(history: RuleEngineConfigHistory) -> RuleEngineConfigHistoryEntry:
    """Convert a config history record to API response."""
    changed = history.changed if history.changed is not None else None

    return RuleEngineConfigHistoryEntry(
        re_id=int(history.re_id),
        label=str(history.label),
        version=int(history.version),
        config=history.config if history.config else {},
        changed=changed,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def field_type_history_to_response(history: FieldTypeHistory) -> FieldTypeHistoryEntry:
    """Convert a field type history record to API response."""
    return FieldTypeHistoryEntry(
        id=int(history.id),
        field_name=str(history.field_name),
        configured_type=str(history.configured_type),
        datetime_format=str(history.datetime_format) if history.datetime_format else None,
        action=str(history.action),
        details=str(history.details) if history.details else None,
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
    )


def role_permission_history_to_response(history: RolePermissionHistory) -> RolePermissionHistoryEntry:
    """Convert a role permission history record to API response."""
    return RolePermissionHistoryEntry(
        id=int(history.id),
        role_id=int(history.role_id),
        role_name=str(history.role_name),
        action=str(history.action),
        details=str(history.details) if history.details else None,
        changed=history.changed if history.changed is not None else None,  # type: ignore[arg-type]
        changed_by=str(history.changed_by) if history.changed_by else None,
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

    total_user_list_actions = db.query(UserListHistory).count()
    total_outcome_actions = db.query(OutcomeHistory).count()
    total_label_actions = db.query(LabelHistory).count()
    total_user_account_actions = db.query(UserAccountHistory).count()
    total_role_permission_actions = db.query(RolePermissionHistory).count()
    total_field_type_actions = db.query(FieldTypeHistory).count()

    return AuditSummaryResponse(
        total_rule_versions=total_rule_versions,
        total_config_versions=total_config_versions,
        rules_with_changes=rules_with_changes,
        configs_with_changes=configs_with_changes,
        total_user_list_actions=total_user_list_actions,
        total_outcome_actions=total_outcome_actions,
        total_label_actions=total_label_actions,
        total_user_account_actions=total_user_account_actions,
        total_role_permission_actions=total_role_permission_actions,
        total_field_type_actions=total_field_type_actions,
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


# =============================================================================
# USER LIST HISTORY
# =============================================================================


@router.get("/user-lists", response_model=UserListAuditListResponse)
def list_user_list_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    list_id: int | None = Query(default=None, description="Filter by user list ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> UserListAuditListResponse:
    """
    Get paginated user list action history.

    Returns all user list changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(UserListHistory)

    if start_date:
        query = query.filter(UserListHistory.changed >= start_date)
    if end_date:
        query = query.filter(UserListHistory.changed <= end_date)
    if list_id:
        query = query.filter(UserListHistory.ul_id == list_id)

    total = query.count()
    items = query.order_by(UserListHistory.changed.desc()).offset(offset).limit(limit).all()

    return UserListAuditListResponse(
        total=total,
        items=[user_list_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


# =============================================================================
# OUTCOME HISTORY
# =============================================================================


@router.get("/outcomes", response_model=OutcomeAuditListResponse)
def list_outcome_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> OutcomeAuditListResponse:
    """
    Get paginated outcome action history.

    Returns all outcome changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(OutcomeHistory)

    if start_date:
        query = query.filter(OutcomeHistory.changed >= start_date)
    if end_date:
        query = query.filter(OutcomeHistory.changed <= end_date)

    total = query.count()
    items = query.order_by(OutcomeHistory.changed.desc()).offset(offset).limit(limit).all()

    return OutcomeAuditListResponse(
        total=total,
        items=[outcome_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


# =============================================================================
# LABEL HISTORY
# =============================================================================


@router.get("/labels", response_model=LabelAuditListResponse)
def list_label_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> LabelAuditListResponse:
    """
    Get paginated label action history.

    Returns all label changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(LabelHistory)

    if start_date:
        query = query.filter(LabelHistory.changed >= start_date)
    if end_date:
        query = query.filter(LabelHistory.changed <= end_date)

    total = query.count()
    items = query.order_by(LabelHistory.changed.desc()).offset(offset).limit(limit).all()

    return LabelAuditListResponse(
        total=total,
        items=[label_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


# =============================================================================
# USER ACCOUNT HISTORY
# =============================================================================


@router.get("/users", response_model=UserAccountAuditListResponse)
def list_user_account_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    user_id: int | None = Query(default=None, description="Filter by target user ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> UserAccountAuditListResponse:
    """
    Get paginated user account action history.

    Returns all user account changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(UserAccountHistory)

    if start_date:
        query = query.filter(UserAccountHistory.changed >= start_date)
    if end_date:
        query = query.filter(UserAccountHistory.changed <= end_date)
    if user_id is not None:
        query = query.filter(UserAccountHistory.user_id == user_id)

    total = query.count()
    items = query.order_by(UserAccountHistory.changed.desc()).offset(offset).limit(limit).all()

    return UserAccountAuditListResponse(
        total=total,
        items=[user_account_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


# =============================================================================
# ROLE PERMISSION HISTORY
# =============================================================================


@router.get("/roles", response_model=RolePermissionAuditListResponse)
def list_role_permission_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    role_id: int | None = Query(default=None, description="Filter by role ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> RolePermissionAuditListResponse:
    """
    Get paginated role permission action history.

    Returns all role and permission changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(RolePermissionHistory)

    if start_date:
        query = query.filter(RolePermissionHistory.changed >= start_date)
    if end_date:
        query = query.filter(RolePermissionHistory.changed <= end_date)
    if role_id is not None:
        query = query.filter(RolePermissionHistory.role_id == role_id)

    total = query.count()
    items = query.order_by(RolePermissionHistory.changed.desc()).offset(offset).limit(limit).all()

    return RolePermissionAuditListResponse(
        total=total,
        items=[role_permission_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )


# =============================================================================
# FIELD TYPE HISTORY
# =============================================================================


@router.get("/field-types", response_model=FieldTypeAuditListResponse)
def list_field_type_history(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.ACCESS_AUDIT_TRAIL)),
    db: Any = Depends(get_db),
    start_date: datetime | None = Query(default=None, description="Filter by start date"),
    end_date: datetime | None = Query(default=None, description="Filter by end date"),
    field_name: str | None = Query(default=None, description="Filter by field name"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> FieldTypeAuditListResponse:
    """
    Get paginated field type config action history.

    Returns all field type configuration changes with optional filtering.
    Requires ACCESS_AUDIT_TRAIL permission.
    """
    query = db.query(FieldTypeHistory)

    if start_date:
        query = query.filter(FieldTypeHistory.changed >= start_date)
    if end_date:
        query = query.filter(FieldTypeHistory.changed <= end_date)
    if field_name is not None:
        query = query.filter(FieldTypeHistory.field_name == field_name)

    total = query.count()
    items = query.order_by(FieldTypeHistory.changed.desc()).offset(offset).limit(limit).all()

    return FieldTypeAuditListResponse(
        total=total,
        items=[field_type_history_to_response(h) for h in items],
        limit=limit,
        offset=offset,
    )
