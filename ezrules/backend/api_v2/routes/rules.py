"""
FastAPI routes for rule management.

These endpoints provide CRUD operations for rules, plus validation and testing.
All endpoints require authentication and appropriate permissions.
"""

import json
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import NoResultFound

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.rules import (
    RuleCreate,
    RuleHistoryEntry,
    RuleHistoryResponse,
    RuleListItem,
    RuleMutationResponse,
    RuleResponse,
    RuleRevisionSummary,
    RulesListResponse,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdate,
    RuleVerifyRequest,
    RuleVerifyResponse,
)
from ezrules.backend.api_v2.schemas.shadow import ShadowDeployRequest, ShadowDeployResponse
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_shadow,
    promote_shadow_rule_to_production,
    remove_rule_from_shadow,
    save_rule_history,
)
from ezrules.core.type_casting import CastError, cast_event
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import RuleEngineConfig, User
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/rules", tags=["Rules"])

# Default limit for history endpoint
HISTORY_LIMIT_DEFAULT = 10


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_rule_manager(db: Any) -> RDBRuleManager:
    """Get a rule manager instance for the current organization."""
    # For now, use o_id=1 as default. In multi-tenant setup, this would come from user context.
    o_id = 1
    return RDBRuleManager(db=db, o_id=o_id)


def get_config_producer(db: Any) -> RDBRuleEngineConfigProducer:
    """Get a config producer instance for updating rule engine config."""
    o_id = 1
    return RDBRuleEngineConfigProducer(db=db, o_id=o_id)


def rule_to_response(rule: RuleModel, revisions: list[RuleRevisionSummary] | None = None) -> RuleResponse:
    """Convert a database rule model to API response."""
    # Cast SQLAlchemy column types to Python types for Pydantic
    created_at = rule.created_at if rule.created_at is not None else None
    return RuleResponse(
        r_id=int(rule.r_id),
        rid=str(rule.rid),
        description=str(rule.description),
        logic=str(rule.logic),
        created_at=created_at,  # type: ignore[arg-type]
        revisions=revisions or [],
    )


# =============================================================================
# LIST RULES
# =============================================================================


@router.get("", response_model=RulesListResponse)
def list_rules(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> RulesListResponse:
    """
    Get all rules.

    Returns a list of all rules in the system, along with the evaluator endpoint URL.
    """
    rule_manager = get_rule_manager(db)
    rules = rule_manager.load_all_rules()

    # Determine which rules are in shadow config
    shadow_r_ids: set[int] = set()
    try:
        shadow_config = (
            db.query(RuleEngineConfig)
            .where(RuleEngineConfig.label == "shadow", RuleEngineConfig.o_id == app_settings.ORG_ID)
            .one()
        )
        shadow_r_ids = {int(r["r_id"]) for r in shadow_config.config if "r_id" in r}
    except Exception:
        pass

    rules_data = [
        RuleListItem(
            r_id=int(rule.r_id),
            rid=str(rule.rid),
            description=str(rule.description),
            logic=str(rule.logic),
            created_at=rule.created_at,  # type: ignore[arg-type]
            in_shadow=int(rule.r_id) in shadow_r_ids,
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
    db: Any = Depends(get_db),
) -> RuleResponse:
    """
    Get a single rule by ID.

    Returns the rule details including its revision history.
    """
    rule_manager = get_rule_manager(db)
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
    db: Any = Depends(get_db),
) -> RuleResponse:
    """
    Get a specific historical revision of a rule.

    Returns the rule as it existed at the specified revision.
    """
    rule_manager = get_rule_manager(db)

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
    db: Any = Depends(get_db),
) -> RuleHistoryResponse:
    """
    Get the revision history of a rule.

    Returns the most recent revisions (up to `limit`) plus the current version.
    Useful for showing a diff timeline of rule changes.
    """
    rule_manager = get_rule_manager(db)

    latest_version = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if latest_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

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
                created_at=rev.created,  # type: ignore[arg-type]
            )
        )

    # Append the current (latest) version
    history.append(
        RuleHistoryEntry(
            revision_number=int(latest_version.version),  # type: ignore[attr-defined]
            logic=str(latest_version.logic),
            description=str(latest_version.description),
            created_at=latest_version.created_at,  # type: ignore[arg-type]
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
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """
    Create a new rule.

    The rule logic will be validated before saving. If validation fails,
    a 400 error is returned with details about what's wrong.
    """
    # Validate the rule logic by trying to compile it
    try:
        rule_config = {
            "rid": rule_data.rid,
            "logic": rule_data.logic,
            "description": rule_data.description,
        }
        RuleFactory.from_json(rule_config)
    except Exception as e:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=f"Invalid rule logic: {e!s}",
        )

    # Create and persist the new rule
    rule_manager = get_rule_manager(db)
    config_producer = get_config_producer(db)

    new_rule = RuleModel(
        rid=rule_data.rid,
        logic=rule_data.logic,
        description=rule_data.description,
    )
    rule_manager.save_rule(new_rule)

    # Update rule engine config
    config_producer.save_config(rule_manager, changed_by=str(user.email))

    return RuleMutationResponse(
        success=True,
        message="Rule created successfully",
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
    db: Any = Depends(get_db),
) -> RuleMutationResponse:
    """
    Update an existing rule.

    Only provided fields will be updated. The rule logic will be validated
    before saving.
    """
    rule_manager = get_rule_manager(db)
    config_producer = get_config_producer(db)

    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    # Apply updates (only if provided)
    new_description = rule_data.description if rule_data.description is not None else rule.description
    new_logic = rule_data.logic if rule_data.logic is not None else rule.logic

    # Validate the rule logic by trying to compile it
    try:
        rule_config = {
            "rid": rule.rid,
            "logic": new_logic,
            "description": new_description,
        }
        RuleFactory.from_json(rule_config)
    except Exception as e:
        return RuleMutationResponse(
            success=False,
            message="Rule validation failed",
            error=f"Invalid rule logic: {e!s}",
        )

    # Snapshot current state before mutation
    save_rule_history(db, rule, changed_by=str(user.email))

    # Apply the mutation and save (version bump handled by rule manager)
    rule.description = new_description
    rule.logic = new_logic
    rule_manager.save_rule(rule)

    # Update rule engine config
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
        message="Rule updated successfully",
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
) -> RuleVerifyResponse:
    """
    Verify rule syntax and extract parameters.

    This endpoint checks if the rule logic is syntactically valid and returns
    the list of parameters (variables) used in the rule.

    This does NOT save the rule - it's just for validation.
    """
    try:
        rule = Rule(rid="", logic=request.rule_source)
        params = sorted(rule.get_rule_params(), key=str)
        return RuleVerifyResponse(params=params)
    except Exception:
        # Return empty params if rule can't be compiled
        return RuleVerifyResponse(params=[])


# =============================================================================
# TEST RULE (execution)
# =============================================================================


@router.post("/test", response_model=RuleTestResponse)
def test_rule(
    request: RuleTestRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> RuleTestResponse:
    """
    Test rule execution against sample data.

    Compiles the rule and executes it against the provided test JSON.
    Applies configured field type casting before execution.
    Returns the rule outcome (True/False) if successful, or an error message.

    This does NOT save the rule - it's just for testing.
    """
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
    record_observations(db, test_object, app_settings.ORG_ID)

    # Apply field type casting
    configs = load_cast_configs(db, app_settings.ORG_ID)
    try:
        test_object = cast_event(test_object, configs)
    except CastError as exc:
        return RuleTestResponse(
            status="error",
            reason=f"Type casting failed: {exc!s}",
            rule_outcome=None,
        )

    # Compile the rule
    try:
        rule = Rule(rid="", logic=request.rule_source)
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

    rule_manager = get_rule_manager(db)
    rule = rule_manager.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    deploy_rule_to_shadow(
        db,
        o_id=app_settings.ORG_ID,
        rule_model=rule,
        changed_by=str(user.email),
        logic_override=request.logic,
        description_override=request.description,
    )

    # Invalidate shadow executor so it reloads on next request
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule.rid} deployed to shadow")


@router.delete("/{rule_id}/shadow", response_model=ShadowDeployResponse)
def remove_from_shadow(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    db: Any = Depends(get_db),
) -> ShadowDeployResponse:
    """Remove a rule from the shadow config."""
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    remove_rule_from_shadow(db, o_id=app_settings.ORG_ID, r_id=rule_id, changed_by=str(user.email))

    # Invalidate shadow executor so it reloads on next request
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule_id} removed from shadow")


@router.post("/{rule_id}/shadow/promote", response_model=ShadowDeployResponse)
def promote_to_production(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    db: Any = Depends(get_db),
) -> ShadowDeployResponse:
    """Promote a rule from shadow config into the production config."""
    from ezrules.backend.api_v2.routes import evaluator as evaluator_module

    try:
        promote_shadow_rule_to_production(db, o_id=app_settings.ORG_ID, r_id=rule_id, changed_by=str(user.email))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Invalidate both executors so they reload on next request
    evaluator_module._lre = None
    evaluator_module._shadow_lre = None

    return ShadowDeployResponse(success=True, message=f"Rule {rule_id} promoted to production")
