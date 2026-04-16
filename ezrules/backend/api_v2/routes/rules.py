"""
FastAPI routes for rule management.

These endpoints provide CRUD operations for rules, plus validation and testing.
All endpoints require authentication and appropriate permissions.
"""

import json
import re
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import NoResultFound

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.rollouts import RolloutDeployRequest, RolloutDeployResponse
from ezrules.backend.api_v2.schemas.rules import (
    MainRuleOrderUpdateRequest,
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
    RuleVerifyError,
    RuleVerifyRequest,
    RuleVerifyResponse,
)
from ezrules.backend.api_v2.schemas.shadow import ShadowDeployRequest, ShadowDeployResponse
from ezrules.backend.runtime_settings import get_auto_promote_active_rule_updates, get_neutral_outcome
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import MissingFieldLookupError, OutcomeReturnSyntaxError, Rule, RuleFactory
from ezrules.core.rule_checkers import AllowedOutcomeReturnVisitor
from ezrules.core.rule_helpers import OutcomeReferenceExtractor, UserListReferenceExtractor
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
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Action, FieldObservation, RoleActions, RuleHistory, RuleStatus, User
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


def get_list_provider(db: Any, org_id: int) -> PersistentUserListManager:
    """Get an org-scoped user-list provider for rule compilation/execution."""
    return PersistentUserListManager(db_session=db, o_id=org_id)


def get_outcome_manager(db: Any, org_id: int) -> DatabaseOutcome:
    """Get an org-scoped outcome manager for rule validation."""
    return DatabaseOutcome(db_session=db, o_id=org_id)


def build_rule_warnings(db: Any, org_id: int, referenced_fields: list[str]) -> list[str]:
    """Return advisory warnings for fields the rule references but traffic has never observed."""
    if not referenced_fields:
        return []

    observed_fields = {
        str(field_name)
        for (field_name,) in db.query(FieldObservation.field_name)
        .filter(FieldObservation.o_id == org_id, FieldObservation.field_name.in_(referenced_fields))
        .distinct()
        .all()
    }
    unseen_fields = [field_name for field_name in referenced_fields if field_name not in observed_fields]
    return [
        (
            f"Field '{field_name}' has not been observed in traffic or test payloads yet. "
            "Backtests will skip historical events where it is missing or null."
        )
        for field_name in unseen_fields
    ]


def unique_preserving_order(items: list[str]) -> list[str]:
    """Return the first occurrence of each item while preserving source order."""
    return list(dict.fromkeys(items))


def extract_referenced_lists(rule_source: str) -> list[str]:
    """Extract @ListName references from rule source without compiling it."""
    return unique_preserving_order(UserListReferenceExtractor().extract(rule_source))


def extract_referenced_outcomes(rule_source: str) -> list[str]:
    """Extract !OUTCOME references from rule source without compiling it."""
    return [outcome.upper() for outcome in unique_preserving_order(OutcomeReferenceExtractor().extract(rule_source))]


def find_reference_bounds(rule_source: str, reference: str) -> tuple[int, int, int, int] | None:
    """Return 1-based line/column bounds for the first matching reference."""
    for line_number, line_text in enumerate(rule_source.splitlines(), start=1):
        start = line_text.find(reference)
        if start == -1:
            continue
        column = start + 1
        end_column = column + len(reference)
        return (line_number, column, line_number, end_column)
    return None


def build_verify_error(
    message: str,
    line: int | None = None,
    column: int | None = None,
    end_line: int | None = None,
    end_column: int | None = None,
) -> RuleVerifyError:
    return RuleVerifyError(
        message=message,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )


def normalize_rule_source_line(line: int | None) -> int | None:
    """Map syntax errors from the wrapped helper function back to user source lines."""
    if line is None:
        return None
    if line <= 1:
        return 1
    return line - 1


def normalize_rule_source_column(column: int | None) -> int | None:
    """Map wrapped helper columns back to user source columns."""
    if column is None:
        return None
    return max(1, column - 1)


def build_outcome_notation_errors(db: Any, org_id: int, rule_source: str) -> list[RuleVerifyError]:
    """Return structured errors for unknown !OUTCOME references."""
    errors: list[RuleVerifyError] = []
    allowed_outcomes = set(get_outcome_manager(db, org_id).get_allowed_outcomes())

    raw_outcome_references = unique_preserving_order(OutcomeReferenceExtractor().extract(rule_source))
    for raw_outcome_name in raw_outcome_references:
        outcome_name = raw_outcome_name.upper()
        if outcome_name in allowed_outcomes:
            continue
        location = find_reference_bounds(rule_source, f"!{raw_outcome_name}")
        errors.append(
            build_verify_error(
                message=f"Outcome '!{outcome_name}' is not configured in Outcomes.",
                line=location[0] if location else None,
                column=location[1] if location else None,
                end_line=location[2] if location else None,
                end_column=location[3] if location else None,
            )
        )

    return errors


def is_active(rule: RuleModel) -> bool:
    """Return True when a rule is currently active."""
    return rule.status == RuleStatus.ACTIVE


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


def validate_allowlist_rule(rule: Rule, allowlist_outcome: str) -> str | None:
    visitor = AllowedOutcomeReturnVisitor()
    visitor.visit(rule._rule_ast)
    if not visitor.values:
        return f"Allowlist rules must contain at least one return !{allowlist_outcome} statement."

    invalid_values = [value for value in visitor.values if value != allowlist_outcome]
    if invalid_values:
        rendered_values = ", ".join(sorted({repr(value) for value in invalid_values}))
        return (
            f"Allowlist rules must return only the configured neutral outcome !{allowlist_outcome}. "
            f"Found {rendered_values}."
        )
    return None


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
    allowlist_outcome = get_neutral_outcome(db, current_org_id)
    outcome_errors = build_outcome_notation_errors(db, current_org_id, rule_data.logic)
    if outcome_errors:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=outcome_errors[0].message,
        )

    # Validate the rule logic by trying to compile it
    try:
        rule_config = {
            "rid": rule_data.rid,
            "logic": rule_data.logic,
            "description": rule_data.description,
        }
        compiled_rule = RuleFactory.from_json(rule_config, list_values_provider=get_list_provider(db, current_org_id))
    except Exception as e:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=f"Invalid rule logic: {e!s}",
        )

    if evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST:
        validation_error = validate_allowlist_rule(compiled_rule, allowlist_outcome)
        if validation_error is not None:
            return RuleMutationResponse(
                success=False,
                message="Rule validation failed",
                error=validation_error,
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
    allowlist_outcome = get_neutral_outcome(db, current_org_id)
    outcome_errors = build_outcome_notation_errors(db, current_org_id, new_logic)
    if outcome_errors:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=outcome_errors[0].message,
        )

    # Validate the rule logic by trying to compile it
    try:
        rule_config = {
            "rid": rule.rid,
            "logic": new_logic,
            "description": new_description,
        }
        compiled_rule = RuleFactory.from_json(rule_config, list_values_provider=get_list_provider(db, current_org_id))
    except Exception as e:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=f"Invalid rule logic: {e!s}",
        )

    if new_evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST:
        validation_error = validate_allowlist_rule(compiled_rule, allowlist_outcome)
        if validation_error is not None:
            return RuleMutationResponse(
                success=False,
                message="Rule validation failed",
                error=validation_error,
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
    """Promote a draft rule to active and record approver metadata."""
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
    referenced_lists = extract_referenced_lists(request.rule_source)
    referenced_outcomes = extract_referenced_outcomes(request.rule_source)
    outcome_errors = build_outcome_notation_errors(db, current_org_id, request.rule_source)
    if outcome_errors:
        return RuleVerifyResponse(
            valid=False,
            params=[],
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=[],
            errors=outcome_errors,
        )
    try:
        rule = Rule(
            rid="",
            logic=request.rule_source,
            list_values_provider=get_list_provider(db, current_org_id),
        )
        params = sorted(rule.get_rule_params(), key=str)
        return RuleVerifyResponse(
            valid=True,
            params=params,
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=build_rule_warnings(db, current_org_id, params),
            errors=[],
        )
    except OutcomeReturnSyntaxError as exc:
        return RuleVerifyResponse(
            valid=False,
            params=[],
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=[],
            errors=[
                build_verify_error(
                    message=str(exc),
                    line=normalize_rule_source_line(exc.lineno),
                    column=normalize_rule_source_column(exc.offset),
                    end_line=normalize_rule_source_line(exc.end_lineno),
                    end_column=normalize_rule_source_column(exc.end_offset),
                )
            ],
        )
    except SyntaxError as exc:
        message = exc.msg or "Rule source is invalid"
        return RuleVerifyResponse(
            valid=False,
            params=[],
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=[],
            errors=[
                build_verify_error(
                    message=message,
                    line=normalize_rule_source_line(exc.lineno),
                    column=normalize_rule_source_column(exc.offset),
                    end_line=normalize_rule_source_line(exc.end_lineno),
                    end_column=normalize_rule_source_column(exc.end_offset),
                )
            ],
        )
    except KeyError as exc:
        message = str(exc.args[0]) if exc.args else "Rule source is invalid"
        missing_list_match = re.search(r"List '([^']+)' not found", message)
        location = None
        if missing_list_match:
            location = find_reference_bounds(request.rule_source, f"@{missing_list_match.group(1)}")
        return RuleVerifyResponse(
            valid=False,
            params=[],
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=[],
            errors=[
                build_verify_error(
                    message=message,
                    line=location[0] if location else None,
                    column=location[1] if location else None,
                    end_line=location[2] if location else None,
                    end_column=location[3] if location else None,
                )
            ],
        )
    except Exception as exc:
        return RuleVerifyResponse(
            valid=False,
            params=[],
            referenced_lists=referenced_lists,
            referenced_outcomes=referenced_outcomes,
            warnings=[],
            errors=[build_verify_error(message=str(exc) or "Rule source is invalid")],
        )


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
