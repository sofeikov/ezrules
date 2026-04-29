"""
FastAPI routes for rule management.

These endpoints provide CRUD operations for rules, plus validation and testing.
All endpoints require authentication and appropriate permissions.
"""

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import NoResultFound

from ezrules.backend.ai_rule_authoring import (
    AIRuleAuthoringProviderError,
    AIRuleAuthoringUnavailableError,
    generate_rule_draft,
)
from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.rollouts import RolloutDeployRequest, RolloutDeployResponse
from ezrules.backend.api_v2.schemas.rules import (
    MainRuleOrderUpdateRequest,
    RuleAIDraftApplyRequest,
    RuleAIDraftApplyResponse,
    RuleAIDraftRequest,
    RuleAIDraftResponse,
    RuleCreate,
    RuleHistoryEntry,
    RuleHistoryResponse,
    RuleListItem,
    RuleMutationResponse,
    RuleReorderResponse,
    RuleResponse,
    RuleRevisionSummary,
    RuleRollbackRequest,
    RulesListResponse,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdate,
    RuleVerifyRequest,
    RuleVerifyResponse,
)
from ezrules.backend.api_v2.schemas.shadow import ShadowDeployRequest, ShadowDeployResponse
from ezrules.backend.rule_validation import (
    build_outcome_notation_errors,
    get_list_provider,
    validate_rule_source,
)
from ezrules.backend.runtime_settings import get_auto_promote_active_rule_updates
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.audit_helpers import save_ai_rule_authoring_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import MissingFieldLookupError, OutcomeReturnSyntaxError, Rule, RuleFactory
from ezrules.core.rule_updater import (
    ROLLOUT_CONFIG_LABEL,
    RULE_EVALUATION_LANE_ALLOWLIST,
    RULE_EVALUATION_LANE_MAIN,
    SHADOW_CONFIG_LABEL,
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_rollout,
    deploy_rule_to_shadow,
    get_candidate_deployment_label,
    list_candidate_deployments,
    promote_rollout_rule_to_production,
    promote_shadow_rule_to_production,
    remove_rule_from_rollout,
    remove_rule_from_shadow,
    save_rule_history,
)
from ezrules.core.type_casting import CastError, RequiredFieldError, normalize_event
from ezrules.models.backend_core import (
    Action,
    AIRuleAuthoringHistory,
    EvaluationRuleResult,
    RoleActions,
    RuleDeploymentResultsLog,
    RuleHistory,
    RuleStatus,
    ShadowResultsLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/rules", tags=["Rules"])

# Default limit for history endpoint
HISTORY_LIMIT_DEFAULT = 10


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_rule_manager(db: Any, org_id: int) -> RDBRuleManager:
    """Get a rule manager instance for the current organization."""
    return RDBRuleManager(db=db, o_id=org_id)


def get_config_producer(db: Any, org_id: int) -> RDBRuleEngineConfigProducer:
    """Get a config producer instance for updating rule engine config."""
    return RDBRuleEngineConfigProducer(db=db, o_id=org_id)


def is_active(rule: RuleModel) -> bool:
    """Return True when a rule is currently active."""
    return rule.status == RuleStatus.ACTIVE


def delete_rule_result_references(db: Any, rule_id: int) -> None:
    """Remove canonical per-rule result rows that would otherwise block hard deletion."""
    for model in (RuleDeploymentResultsLog, ShadowResultsLog, EvaluationRuleResult):
        db.query(model).filter(model.r_id == rule_id).delete(synchronize_session=False)


def user_has_permission(db: Any, user: User, action: PermissionAction) -> bool:
    """Return True when the current user has the requested permission."""
    db_action = db.query(Action).filter_by(name=action.value).first()
    if db_action is None:
        return False

    for role in user.roles:
        role_action = (
            db.query(RoleActions)
            .filter_by(role_id=role.id, action_id=db_action.id)
            .filter(RoleActions.resource_id.is_(None))
            .first()
        )
        if role_action is not None:
            return True

    return False


def get_status(status_value: RuleStatus | str) -> RuleStatus:
    """Normalize a status value from ORM objects for schema responses."""
    if isinstance(status_value, RuleStatus):
        return status_value
    return RuleStatus(str(status_value))


def rule_to_response(rule: RuleModel, revisions: list[RuleRevisionSummary] | None = None) -> RuleResponse:
    """Convert a database rule model to API response."""
    # Cast SQLAlchemy column types to Python types for Pydantic
    created_at = rule.created_at if rule.created_at is not None else None
    return RuleResponse(
        r_id=int(rule.r_id),
        rid=str(rule.rid),
        description=str(rule.description),
        logic=str(rule.logic),
        execution_order=int(getattr(rule, "execution_order", 1) or 1),
        evaluation_lane=str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN),
        status=get_status(rule.status),
        effective_from=rule.effective_from if rule.effective_from is not None else None,  # type: ignore[arg-type]
        approved_by=int(rule.approved_by) if rule.approved_by is not None else None,
        approved_at=rule.approved_at if rule.approved_at is not None else None,  # type: ignore[arg-type]
        created_at=created_at,  # type: ignore[arg-type]
        revisions=revisions or [],
    )


def ensure_no_active_candidate_deployment(db: Any, org_id: int, rule_id: int) -> None:
    deployment_label = get_candidate_deployment_label(db, o_id=org_id, r_id=rule_id)
    if deployment_label is None:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Rule has an active {deployment_label} deployment. Remove or promote it before changing the base rule.",
    )


def normalize_evaluation_lane(value: str | None) -> str:
    lane = str(value or RULE_EVALUATION_LANE_MAIN).strip().lower()
    if lane not in {RULE_EVALUATION_LANE_MAIN, RULE_EVALUATION_LANE_ALLOWLIST}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="evaluation_lane must be either 'main' or 'allowlist'",
        )
    return lane


def normalize_ai_authoring_mode(value: str | None) -> str:
    mode = str(value or "create").strip().lower()
    if mode not in {"create", "edit"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be either 'create' or 'edit'",
        )
    return mode


def _next_execution_order(db: Any, org_id: int, lane: str) -> int:
    max_order = (
        db.query(RuleModel.execution_order)
        .filter(
            RuleModel.o_id == org_id,
            RuleModel.evaluation_lane == lane,
        )
        .order_by(RuleModel.execution_order.desc(), RuleModel.r_id.desc())
        .first()
    )
    return int(max_order[0]) + 1 if max_order and max_order[0] is not None else 1


def _list_main_rules_in_execution_order(db: Any, org_id: int) -> list[RuleModel]:
    return (
        db.query(RuleModel)
        .filter(
            RuleModel.o_id == org_id,
            RuleModel.evaluation_lane == RULE_EVALUATION_LANE_MAIN,
            RuleModel.status != RuleStatus.ARCHIVED,
        )
        .order_by(RuleModel.execution_order.asc(), RuleModel.r_id.asc())
        .all()
    )


def validate_execution_order_for_lane(evaluation_lane: str, execution_order: int | None) -> str | None:
    if evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST and execution_order is not None:
        return "execution_order is supported only for main rules."
    return None


@router.put("/main-order", response_model=RuleReorderResponse)
def update_main_rule_order(
    request_data: MainRuleOrderUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.REORDER_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleReorderResponse:
    """Replace the full ordered main-rule sequence for the current organization."""
    main_rules = _list_main_rules_in_execution_order(db, current_org_id)
    current_ids = [int(rule.r_id) for rule in main_rules]
    requested_ids = [int(rule_id) for rule_id in request_data.ordered_r_ids]

    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Main rule order contains duplicate IDs")

    if requested_ids != current_ids and sorted(requested_ids) != sorted(current_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Main rule order update must include every existing main rule exactly once",
        )

    by_id = {int(rule.r_id): rule for rule in main_rules}
    changed_rules = [
        by_id[rule_id]
        for execution_order, rule_id in enumerate(requested_ids, start=1)
        if int(by_id[rule_id].execution_order) != execution_order
    ]

    if not changed_rules:
        return RuleReorderResponse(
            success=True,
            message="Main rule order unchanged.",
        )

    for rule in changed_rules:
        save_rule_history(
            db,
            rule,
            changed_by=str(user.email),
            action="reordered",
        )

    for execution_order, rule_id in enumerate(requested_ids, start=1):
        rule = by_id[rule_id]
        rule.execution_order = execution_order
        if rule in changed_rules:
            rule.version += 1

    get_config_producer(db, current_org_id).save_config(
        get_rule_manager(db, current_org_id), changed_by=str(user.email)
    )

    return RuleReorderResponse(
        success=True,
        message="Main rule order updated.",
    )


# =============================================================================
# LIST RULES
# =============================================================================


@router.get("", response_model=RulesListResponse)
def list_rules(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RulesListResponse:
    """
    Get all rules.

    Returns a list of all rules in the system, along with the evaluator endpoint URL.
    """
    rule_manager = get_rule_manager(db, current_org_id)
    rules = rule_manager.load_all_rules()
    rules = sorted(
        rules,
        key=lambda rule: (
            0 if str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN)) == RULE_EVALUATION_LANE_MAIN else 1,
            int(getattr(rule, "execution_order", 1) or 1),
            int(rule.r_id),
        ),
    )

    shadow_r_ids = {
        int(entry["r_id"])
        for entry in list_candidate_deployments(db, current_org_id, SHADOW_CONFIG_LABEL)
        if "r_id" in entry
    }
    rollout_entries = {
        int(entry["r_id"]): entry
        for entry in list_candidate_deployments(db, current_org_id, ROLLOUT_CONFIG_LABEL)
        if "r_id" in entry
    }

    rules_data = [
        RuleListItem(
            r_id=int(rule.r_id),
            rid=str(rule.rid),
            description=str(rule.description),
            logic=str(rule.logic),
            execution_order=int(getattr(rule, "execution_order", 1) or 1),
            evaluation_lane=str(
                getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN
            ),
            status=get_status(rule.status),
            effective_from=rule.effective_from if rule.effective_from is not None else None,  # type: ignore[arg-type]
            approved_by=int(rule.approved_by) if rule.approved_by is not None else None,
            approved_at=rule.approved_at if rule.approved_at is not None else None,  # type: ignore[arg-type]
            created_at=rule.created_at,  # type: ignore[arg-type]
            in_shadow=int(rule.r_id) in shadow_r_ids,
            in_rollout=int(rule.r_id) in rollout_entries,
            rollout_percent=int(rollout_entries[int(rule.r_id)]["traffic_percent"])
            if int(rule.r_id) in rollout_entries and rollout_entries[int(rule.r_id)].get("traffic_percent") is not None
            else None,
        )
        for rule in rules
    ]

    return RulesListResponse(
        rules=rules_data,
        evaluator_endpoint=app_settings.EVALUATOR_ENDPOINT,
    )


# =============================================================================
# GET SINGLE RULE
# =============================================================================


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleResponse:
    """
    Get a single rule by ID.

    Returns the rule details including its revision history.
    """
    rule_manager = get_rule_manager(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    # Get revision list
    revision_list = rule_manager.get_rule_revision_list(rule)
    revisions = [
        RuleRevisionSummary(
            revision_number=rev.revision_number,
            created_at=rev.created,  # type: ignore[arg-type]
        )
        for rev in revision_list
    ]

    return rule_to_response(rule, revisions)


# =============================================================================
# GET RULE REVISION
# =============================================================================


@router.get("/{rule_id}/revisions/{revision_number}", response_model=RuleResponse)
def get_rule_revision(
    rule_id: int,
    revision_number: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleResponse:
    """
    Get a specific historical revision of a rule.

    Returns the rule as it existed at the specified revision.
    """
    rule_manager = get_rule_manager(db, current_org_id)

    try:
        rule = rule_manager.load_rule(rule_id, revision_number=revision_number)  # type: ignore[arg-type]
    except NoResultFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule or revision not found",
        ) from e

    created_at = rule.created_at if hasattr(rule, "created_at") else None
    return RuleResponse(
        r_id=rule_id,
        rid=str(rule.rid),
        description=str(rule.description),
        logic=str(rule.logic),
        execution_order=int(getattr(rule, "execution_order", 1) or 1),
        evaluation_lane=str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN),
        status=get_status(rule.status),
        effective_from=rule.effective_from if hasattr(rule, "effective_from") else None,  # type: ignore[arg-type]
        approved_by=int(rule.approved_by) if getattr(rule, "approved_by", None) is not None else None,
        approved_at=rule.approved_at if hasattr(rule, "approved_at") else None,  # type: ignore[arg-type]
        created_at=created_at,  # type: ignore[arg-type]
        revisions=[],  # Don't include revision list for historical versions
        revision_number=revision_number,
    )


# =============================================================================
# GET RULE HISTORY
# =============================================================================


@router.get("/{rule_id}/history", response_model=RuleHistoryResponse)
def get_rule_history(
    rule_id: int,
    limit: int = Query(default=HISTORY_LIMIT_DEFAULT, ge=1, le=100, description="Max revisions to return"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleHistoryResponse:
    """
    Get the revision history of a rule.

    Returns the most recent revisions (up to `limit`) plus the current version.
    Useful for showing a diff timeline of rule changes.
    """
    rule_manager = get_rule_manager(db, current_org_id)

    latest_version = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if latest_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    latest_history_entry = (
        db.query(RuleHistory)
        .filter(RuleHistory.r_id == rule_id, RuleHistory.o_id == current_org_id)
        .order_by(RuleHistory.version.desc())
        .first()
    )
    current_created_at = latest_history_entry.changed if latest_history_entry is not None else latest_version.created_at

    revision_list = rule_manager.get_rule_revision_list(latest_version)

    # Take only the most recent `limit` revisions (revision_list is oldest-first)
    trimmed_revisions = revision_list[-limit:] if len(revision_list) > limit else revision_list

    history: list[RuleHistoryEntry] = []
    for rev in trimmed_revisions:
        try:
            rule = rule_manager.load_rule(rule_id, revision_number=rev.revision_number)  # type: ignore[arg-type]
        except NoResultFound:
            continue
        history.append(
            RuleHistoryEntry(
                revision_number=rev.revision_number,
                logic=str(rule.logic),
                description=str(rule.description),
                execution_order=int(getattr(rule, "execution_order", 1) or 1),
                evaluation_lane=str(
                    getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN
                ),
                status=get_status(rule.status),
                effective_from=rule.effective_from if hasattr(rule, "effective_from") else None,  # type: ignore[arg-type]
                approved_by=int(rule.approved_by) if getattr(rule, "approved_by", None) is not None else None,
                approved_at=rule.approved_at if hasattr(rule, "approved_at") else None,  # type: ignore[arg-type]
                created_at=rev.created,  # type: ignore[arg-type]
            )
        )

    # Append the current (latest) version
    history.append(
        RuleHistoryEntry(
            revision_number=int(latest_version.version),  # type: ignore[attr-defined]
            logic=str(latest_version.logic),
            description=str(latest_version.description),
            execution_order=int(getattr(latest_version, "execution_order", 1) or 1),
            evaluation_lane=str(
                getattr(latest_version, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN
            ),
            status=get_status(latest_version.status),
            effective_from=latest_version.effective_from if latest_version.effective_from is not None else None,  # type: ignore[arg-type]
            approved_by=int(latest_version.approved_by) if latest_version.approved_by is not None else None,
            approved_at=latest_version.approved_at if latest_version.approved_at is not None else None,  # type: ignore[arg-type]
            created_at=current_created_at,  # type: ignore[arg-type]
            is_current=True,
        )
    )

    return RuleHistoryResponse(
        r_id=rule_id,
        rid=str(latest_version.rid),
        history=history,
    )


# =============================================================================
# CREATE RULE
# =============================================================================


@router.post("", response_model=RuleMutationResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    rule_data: RuleCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """
    Create a new rule.

    The rule logic will be validated before saving. If validation fails,
    a 400 error is returned with details about what's wrong.
    """
    evaluation_lane = normalize_evaluation_lane(rule_data.evaluation_lane)
    execution_order_error = validate_execution_order_for_lane(evaluation_lane, rule_data.execution_order)
    if execution_order_error is not None:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=execution_order_error,
        )
    validation = validate_rule_source(
        db,
        current_org_id,
        rule_data.logic,
        evaluation_lane=evaluation_lane,
        rid=rule_data.rid,
        description=rule_data.description,
    )
    if not validation.response.valid or validation.response.errors:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=validation.response.errors[0].message if validation.response.errors else "Invalid rule logic",
        )

    # Create and persist the new rule
    rule_manager = get_rule_manager(db, current_org_id)
    execution_order = (
        int(rule_data.execution_order)
        if rule_data.execution_order is not None
        else _next_execution_order(db, current_org_id, evaluation_lane)
    )
    new_rule = RuleModel(
        rid=rule_data.rid,
        logic=rule_data.logic,
        description=rule_data.description,
        execution_order=execution_order,
        evaluation_lane=evaluation_lane,
        status=RuleStatus.DRAFT,
        effective_from=None,
        approved_by=None,
        approved_at=None,
    )
    rule_manager.save_rule(new_rule)

    return RuleMutationResponse(
        success=True,
        message="Rule created in draft status",
        rule=rule_to_response(new_rule, []),
    )


# =============================================================================
# UPDATE RULE
# =============================================================================


@router.put("/{rule_id}", response_model=RuleMutationResponse)
def update_rule(
    rule_id: int,
    rule_data: RuleUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """
    Update an existing rule.

    Only provided fields will be updated. The rule logic will be validated
    before saving.
    """
    rule_manager = get_rule_manager(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)
    config_producer = get_config_producer(db, current_org_id)
    if rule.status == RuleStatus.ARCHIVED:
        return RuleMutationResponse(
            success=False,
            message="Archived rules cannot be updated",
            error="Archived rules cannot be modified",
        )

    was_active = is_active(rule)
    auto_promote_active_updates = was_active and get_auto_promote_active_rule_updates(db, current_org_id)
    if auto_promote_active_updates and not user_has_permission(db, user, PermissionAction.PROMOTE_RULES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PROMOTE_RULES permission is required to update active rules when auto-promotion is enabled",
        )

    # Apply updates (only if provided)
    new_description = rule_data.description if rule_data.description is not None else rule.description
    new_logic = rule_data.logic if rule_data.logic is not None else rule.logic
    new_evaluation_lane = normalize_evaluation_lane(
        rule_data.evaluation_lane
        if rule_data.evaluation_lane is not None
        else str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN)
    )
    execution_order_error = validate_execution_order_for_lane(new_evaluation_lane, rule_data.execution_order)
    if execution_order_error is not None:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=execution_order_error,
        )
    if rule_data.execution_order is not None:
        new_execution_order = int(rule_data.execution_order)
    elif new_evaluation_lane != str(
        getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN
    ):
        new_execution_order = _next_execution_order(db, current_org_id, new_evaluation_lane)
    else:
        new_execution_order = int(getattr(rule, "execution_order", 1) or 1)
    validation = validate_rule_source(
        db,
        current_org_id,
        new_logic,
        evaluation_lane=new_evaluation_lane,
        rid=str(rule.rid),
        description=str(new_description),
    )
    if not validation.response.valid or validation.response.errors:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=validation.response.errors[0].message if validation.response.errors else "Invalid rule logic",
        )

    promoted_at = datetime.now(UTC) if auto_promote_active_updates else None
    next_status = (
        RuleStatus.ACTIVE
        if auto_promote_active_updates
        else RuleStatus.PAUSED
        if rule.status == RuleStatus.PAUSED
        else RuleStatus.DRAFT
    )

    # Snapshot current state before mutation
    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="updated",
        to_status=next_status,
        effective_from_override=promoted_at,
        approved_by_override=int(user.id) if auto_promote_active_updates else None,
        approved_at_override=promoted_at,
    )

    # Apply the mutation and save (version bump handled by rule manager)
    rule.description = new_description
    rule.logic = new_logic
    rule.execution_order = new_execution_order
    rule.evaluation_lane = new_evaluation_lane
    rule.status = next_status
    rule.effective_from = promoted_at
    rule.approved_by = user.id if auto_promote_active_updates else None
    rule.approved_at = promoted_at
    rule_manager.save_rule(rule)

    # Editing an active rule either updates production in place or removes the rule until it is re-promoted.
    if was_active:
        config_producer.save_config(rule_manager, changed_by=str(user.email))

    # Get updated revision list
    revision_list = rule_manager.get_rule_revision_list(rule)
    revisions = [
        RuleRevisionSummary(
            revision_number=rev.revision_number,
            created_at=rev.created,
        )
        for rev in revision_list
    ]

    return RuleMutationResponse(
        success=True,
        message=(
            "Rule updated and kept active."
            if auto_promote_active_updates
            else "Rule updated and remains paused."
            if next_status == RuleStatus.PAUSED
            else "Rule updated in draft status. Promote to activate."
        ),
        rule=rule_to_response(rule, revisions),
    )


# =============================================================================
# DELETE RULE
# =============================================================================


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> None:
    """
    Delete a rule and keep its audit history.
    """
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)

    was_active = is_active(rule)

    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="deleted",
        to_status=None,
    )

    remove_rule_from_shadow(db, o_id=current_org_id, r_id=rule_id, changed_by=str(user.email))
    delete_rule_result_references(db, rule_id)

    db.delete(rule)
    db.commit()

    if was_active:
        config_producer.save_config(rule_manager, changed_by=str(user.email))


# =============================================================================
# RULE LIFECYCLE ENDPOINTS
# =============================================================================


@router.post("/{rule_id}/promote", response_model=RuleMutationResponse)
def promote_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """Promote a draft rule to active and record who activated it."""
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)
    if rule.status == RuleStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived rules cannot be promoted")
    if rule.status == RuleStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paused rules must be resumed")
    if rule.status == RuleStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule is already active")

    promoted_at = datetime.now(UTC)
    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="promoted",
        to_status=RuleStatus.ACTIVE,
        effective_from_override=promoted_at,
        approved_by_override=int(user.id),
        approved_at_override=promoted_at,
    )
    rule.status = RuleStatus.ACTIVE
    rule.effective_from = promoted_at
    rule.approved_by = user.id
    rule.approved_at = promoted_at
    rule_manager.save_rule(rule)
    config_producer.save_config(rule_manager, changed_by=str(user.email))

    return RuleMutationResponse(
        success=True,
        message="Rule promoted to active",
        rule=rule_to_response(rule),
    )


@router.post("/{rule_id}/pause", response_model=RuleMutationResponse)
def pause_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PAUSE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """Pause an active rule without archiving it."""
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)
    if rule.status == RuleStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived rules cannot be paused")
    if rule.status == RuleStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Draft rules cannot be paused")
    if rule.status == RuleStatus.PAUSED:
        return RuleMutationResponse(success=True, message="Rule already paused", rule=rule_to_response(rule))

    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="paused",
        to_status=RuleStatus.PAUSED,
    )
    rule.status = RuleStatus.PAUSED
    rule.effective_from = None
    rule.approved_by = None
    rule.approved_at = None
    rule_manager.save_rule(rule)
    config_producer.save_config(rule_manager, changed_by=str(user.email))

    return RuleMutationResponse(
        success=True,
        message="Rule paused",
        rule=rule_to_response(rule),
    )


@router.post("/{rule_id}/resume", response_model=RuleMutationResponse)
def resume_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """Resume a paused rule and restore it to active status."""
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)
    if rule.status == RuleStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived rules cannot be resumed")
    if rule.status == RuleStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Draft rules cannot be resumed")
    if rule.status == RuleStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule is already active")

    resumed_at = datetime.now(UTC)
    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="resumed",
        to_status=RuleStatus.ACTIVE,
        effective_from_override=resumed_at,
        approved_by_override=int(user.id),
        approved_at_override=resumed_at,
    )
    rule.status = RuleStatus.ACTIVE
    rule.effective_from = resumed_at
    rule.approved_by = user.id
    rule.approved_at = resumed_at
    rule_manager.save_rule(rule)
    config_producer.save_config(rule_manager, changed_by=str(user.email))

    return RuleMutationResponse(
        success=True,
        message="Rule resumed to active",
        rule=rule_to_response(rule),
    )


@router.post("/{rule_id}/archive", response_model=RuleMutationResponse)
def archive_rule(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """Archive a rule and remove it from production config if active."""
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)
    if rule.status == RuleStatus.ARCHIVED:
        return RuleMutationResponse(success=True, message="Rule already archived", rule=rule_to_response(rule))

    was_active = is_active(rule)
    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="deactivated",
        to_status=RuleStatus.ARCHIVED,
    )
    rule.status = RuleStatus.ARCHIVED
    rule_manager.save_rule(rule)

    remove_rule_from_shadow(db, o_id=current_org_id, r_id=rule_id, changed_by=str(user.email))

    if was_active:
        config_producer.save_config(rule_manager, changed_by=str(user.email))

    return RuleMutationResponse(
        success=True,
        message="Rule archived",
        rule=rule_to_response(rule),
    )


@router.post("/{rule_id}/rollback", response_model=RuleMutationResponse)
def rollback_rule(
    rule_id: int,
    rollback_data: RuleRollbackRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """Create a new draft version from a historical revision."""
    rule_manager = get_rule_manager(db, current_org_id)
    config_producer = get_config_producer(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    ensure_no_active_candidate_deployment(db, current_org_id, rule_id)

    if rollback_data.revision_number == int(rule.version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot roll back to the current revision",
        )

    try:
        target_revision = rule_manager.load_rule(rule_id, revision_number=rollback_data.revision_number)  # type: ignore[arg-type]
    except NoResultFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Historical revision not found",
        ) from e

    try:
        RuleFactory.from_json(
            {
                "rid": rule.rid,
                "logic": target_revision.logic,
                "description": target_revision.description,
            },
            list_values_provider=get_list_provider(db, current_org_id),
        )
    except Exception as e:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=f"Invalid historical rule logic: {e!s}",
        )

    was_active = is_active(rule)
    save_rule_history(
        db,
        rule,
        changed_by=str(user.email),
        action="rolled_back",
        to_status=RuleStatus.DRAFT,
    )
    rule.logic = str(target_revision.logic)
    rule.description = str(target_revision.description)
    rule.evaluation_lane = str(
        getattr(target_revision, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN
    )
    rule.execution_order = int(getattr(target_revision, "execution_order", 1) or 1)
    rule.status = RuleStatus.DRAFT
    rule.effective_from = None
    rule.approved_by = None
    rule.approved_at = None
    rule_manager.save_rule(rule)

    if was_active:
        config_producer.save_config(rule_manager, changed_by=str(user.email))

    revision_list = rule_manager.get_rule_revision_list(rule)
    revisions = [
        RuleRevisionSummary(
            revision_number=rev.revision_number,
            created_at=rev.created,
        )
        for rev in revision_list
    ]

    return RuleMutationResponse(
        success=True,
        message=f"Rule rolled back to revision {rollback_data.revision_number} in draft status. Promote to activate.",
        rule=rule_to_response(rule, revisions),
    )


# =============================================================================
# VERIFY RULE (syntax check)
# =============================================================================


@router.post("/verify", response_model=RuleVerifyResponse)
def verify_rule(
    request: RuleVerifyRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleVerifyResponse:
    """
    Verify rule syntax and extract parameters.

    This endpoint checks if the rule logic is syntactically valid and returns
    the list of parameters (variables) used in the rule.

    This does NOT save the rule - it's just for validation.
    """
    return validate_rule_source(db, current_org_id, request.rule_source).response


@router.post("/ai/draft", response_model=RuleAIDraftResponse)
def generate_ai_rule_draft(
    request: RuleAIDraftRequest,
    user: User = Depends(get_current_active_user),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleAIDraftResponse:
    mode = normalize_ai_authoring_mode(request.mode)
    required_permission = PermissionAction.CREATE_RULE if mode == "create" else PermissionAction.MODIFY_RULE
    if not user_has_permission(db, user, required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{required_permission.value.upper()} permission is required for AI rule authoring in {mode} mode",
        )

    if request.rule_id is not None:
        existing_rule = get_rule_manager(db, current_org_id).load_rule(request.rule_id)  # type: ignore[arg-type]
        if existing_rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    evaluation_lane = normalize_evaluation_lane(request.evaluation_lane)
    try:
        result = generate_rule_draft(
            db,
            current_org_id,
            prompt=request.prompt,
            mode=mode,
            evaluation_lane=evaluation_lane,
            current_logic=request.current_logic,
            current_description=request.current_description,
        )
    except AIRuleAuthoringUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIRuleAuthoringProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    save_ai_rule_authoring_history(
        db,
        generation_id=result.generation_id,
        r_id=request.rule_id,
        action="draft_generated",
        mode=mode,
        evaluation_lane=evaluation_lane,
        provider=result.provider,
        model=result.model,
        prompt_excerpt=result.prompt_excerpt,
        prompt_hash=result.prompt_hash,
        validation_status="valid" if result.applyable else "invalid",
        repair_attempted=result.repair_attempted,
        applyable=result.applyable,
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
    )
    db.commit()

    return RuleAIDraftResponse(
        generation_id=result.generation_id,
        draft_logic=result.draft_logic,
        line_explanations=[
            {
                "line_number": explanation.line_number,
                "source": explanation.source,
                "explanation": explanation.explanation,
            }
            for explanation in result.line_explanations
        ],
        validation=result.validation,
        repair_attempted=result.repair_attempted,
        applyable=result.applyable,
        provider=result.provider,
    )


@router.post("/ai/apply", response_model=RuleAIDraftApplyResponse)
def record_ai_rule_draft_applied(
    request: RuleAIDraftApplyRequest,
    user: User = Depends(get_current_active_user),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleAIDraftApplyResponse:
    generation = (
        db.query(AIRuleAuthoringHistory)
        .filter(
            AIRuleAuthoringHistory.o_id == current_org_id,
            AIRuleAuthoringHistory.generation_id == request.generation_id,
            AIRuleAuthoringHistory.action == "draft_generated",
        )
        .order_by(AIRuleAuthoringHistory.changed.desc(), AIRuleAuthoringHistory.id.desc())
        .first()
    )
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated AI draft not found")
    if not bool(generation.applyable):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only applyable AI drafts can be applied")

    required_permission = PermissionAction.CREATE_RULE if generation.mode == "create" else PermissionAction.MODIFY_RULE
    if not user_has_permission(db, user, required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{required_permission.value.upper()} permission is required to apply this AI draft",
        )

    resolved_rule_id = (
        int(request.rule_id) if request.rule_id is not None else int(generation.r_id) if generation.r_id else None
    )
    if resolved_rule_id is not None:
        existing_rule = get_rule_manager(db, current_org_id).load_rule(resolved_rule_id)  # type: ignore[arg-type]
        if existing_rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    save_ai_rule_authoring_history(
        db,
        generation_id=str(generation.generation_id),
        r_id=resolved_rule_id,
        action="draft_applied",
        mode=str(generation.mode),
        evaluation_lane=str(generation.evaluation_lane),
        provider=str(generation.provider),
        model=str(generation.model),
        prompt_excerpt=str(generation.prompt_excerpt) if generation.prompt_excerpt else None,
        prompt_hash=str(generation.prompt_hash),
        validation_status=str(generation.validation_status),
        repair_attempted=bool(generation.repair_attempted),
        applyable=bool(generation.applyable),
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
    )
    db.commit()

    return RuleAIDraftApplyResponse(success=True, message="AI draft applied to the editor")


# =============================================================================
# TEST RULE (execution)
# =============================================================================


@router.post("/test", response_model=RuleTestResponse)
def test_rule(
    request: RuleTestRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleTestResponse:
    """
    Test rule execution against sample data.

    Compiles the rule and executes it against the provided test JSON.
    Applies configured field type casting before execution.
    Returns the rule outcome (True/False) if successful, or an error message.

    This does NOT save the rule - it's just for testing.
    """
    outcome_errors = build_outcome_notation_errors(db, current_org_id, request.rule_source)
    if outcome_errors:
        return RuleTestResponse(
            status="error",
            reason=outcome_errors[0].message,
            rule_outcome=None,
        )

    # Parse the test JSON
    try:
        test_object = json.loads(request.test_json)
    except JSONDecodeError:
        return RuleTestResponse(
            status="error",
            reason="Example is malformed",
            rule_outcome=None,
        )

    # Record field observations from the raw test JSON (pre-cast types)
    record_observations(db, test_object, current_org_id)

    # Apply field type casting
    configs = load_cast_configs(db, current_org_id)
    try:
        test_object = normalize_event(test_object, configs)
    except (CastError, RequiredFieldError) as exc:
        return RuleTestResponse(
            status="error",
            reason=f"Event normalization failed: {exc!s}",
            rule_outcome=None,
        )

    # Compile the rule
    try:
        rule = Rule(
            rid="",
            logic=request.rule_source,
            list_values_provider=get_list_provider(db, current_org_id),
        )
    except OutcomeReturnSyntaxError as exc:
        return RuleTestResponse(
            status="error",
            reason=str(exc),
            rule_outcome=None,
        )
    except SyntaxError:
        return RuleTestResponse(
            status="error",
            reason="Rule source is invalid",
            rule_outcome=None,
        )

    # Execute the rule
    try:
        rule_outcome = rule(test_object)
        return RuleTestResponse(
            status="ok",
            reason="ok",
            rule_outcome=str(rule_outcome) if rule_outcome is not None else None,
        )
    except MissingFieldLookupError as exc:
        return RuleTestResponse(
            status="error",
            reason=str(exc),
            rule_outcome=None,
        )
    except Exception as e:
        return RuleTestResponse(
            status="error",
            reason=f"Rule execution failed: {e!s}",
            rule_outcome=None,
        )


# =============================================================================
# SHADOW DEPLOYMENT ENDPOINTS
# =============================================================================


@router.post("/{rule_id}/shadow", response_model=ShadowDeployResponse)
def deploy_to_shadow(
    rule_id: int,
    request: ShadowDeployRequest = None,  # type: ignore[assignment]
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowDeployResponse:
    """Deploy a rule to the shadow config for live observation.

    If logic/description are provided in the request body they are stored in
    shadow as-is (the rules table and production config are left unchanged).
    This allows deploying a draft edit directly to shadow without saving to
    production first.
    """
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    if request is None:
        request = ShadowDeployRequest()

    rule_manager = get_rule_manager(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    if rule.status == RuleStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived rules cannot be deployed")
    if str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN) == (
        RULE_EVALUATION_LANE_ALLOWLIST
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allowlist rules cannot be deployed")
    if request.logic is not None:
        outcome_errors = build_outcome_notation_errors(db, current_org_id, request.logic)
        if outcome_errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=outcome_errors[0].message)

    try:
        deploy_rule_to_shadow(
            db,
            o_id=current_org_id,
            rule_model=rule,
            changed_by=str(user.email),
            logic_override=request.logic,
            description_override=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Invalidate shadow executor so it reloads on next request
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule.rid} deployed to shadow")


@router.delete("/{rule_id}/shadow", response_model=ShadowDeployResponse)
def remove_from_shadow(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowDeployResponse:
    """Remove a rule from the shadow config."""
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    remove_rule_from_shadow(db, o_id=current_org_id, r_id=rule_id, changed_by=str(user.email))

    # Invalidate shadow executor so it reloads on next request
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule_id} removed from shadow")


@router.post("/{rule_id}/shadow/promote", response_model=ShadowDeployResponse)
def promote_to_production(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowDeployResponse:
    """Promote a rule from shadow config into the production config."""
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    try:
        promote_shadow_rule_to_production(
            db,
            o_id=current_org_id,
            r_id=rule_id,
            changed_by=str(user.email),
            approved_by=int(user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Invalidate both executors so they reload on next request
    evaluator_module._lre = None
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule_id} promoted to production")


@router.post("/{rule_id}/rollout", response_model=RolloutDeployResponse)
def deploy_to_rollout(
    rule_id: int,
    request: RolloutDeployRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutDeployResponse:
    rule_manager = get_rule_manager(db, current_org_id)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    if rule.status != RuleStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active rules can be rolled out")
    if str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN) == (
        RULE_EVALUATION_LANE_ALLOWLIST
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allowlist rules cannot be rolled out",
        )
    if request.logic is not None:
        outcome_errors = build_outcome_notation_errors(db, current_org_id, request.logic)
        if outcome_errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=outcome_errors[0].message)

    try:
        deploy_rule_to_rollout(
            db,
            o_id=current_org_id,
            rule_model=rule,
            traffic_percent=request.traffic_percent,
            changed_by=str(user.email),
            logic_override=request.logic,
            description_override=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return RolloutDeployResponse(
        success=True,
        message=f"Rule {rule.rid} rollout set to {request.traffic_percent}%",
    )


@router.delete("/{rule_id}/rollout", response_model=RolloutDeployResponse)
def remove_from_rollout(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutDeployResponse:
    remove_rule_from_rollout(db, o_id=current_org_id, r_id=rule_id, changed_by=str(user.email))
    return RolloutDeployResponse(success=True, message=f"Rule {rule_id} removed from rollout")


@router.post("/{rule_id}/rollout/promote", response_model=RolloutDeployResponse)
def promote_rollout_to_production(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.PROMOTE_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutDeployResponse:
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    try:
        promote_rollout_rule_to_production(
            db,
            o_id=current_org_id,
            r_id=rule_id,
            changed_by=str(user.email),
            approved_by=int(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    evaluator_module._lre = None
    evaluator_module._shadow_lre = None

    return RolloutDeployResponse(success=True, message=f"Rule {rule_id} rollout promoted to production")
