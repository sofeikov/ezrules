"""FastAPI routes for runtime settings and rule-quality pair catalog management."""

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.settings import (
    InvalidAllowlistRule,
    OutcomeHierarchyItem,
    OutcomeHierarchyResponse,
    OutcomeHierarchyUpdateRequest,
    RuleQualityPairCreateRequest,
    RuleQualityPairOptionsResponse,
    RuleQualityPairResponse,
    RuleQualityPairsListResponse,
    RuleQualityPairUpdateRequest,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from ezrules.backend.runtime_settings import (
    AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
    MAIN_RULE_EXECUTION_MODE_DEFAULT,
    NEUTRAL_OUTCOME_DEFAULT,
    get_auto_promote_active_rule_updates,
    get_main_rule_execution_mode,
    get_neutral_outcome,
    get_rule_quality_lookback_days,
    set_auto_promote_active_rule_updates,
    set_main_rule_execution_mode,
    set_neutral_outcome,
    set_rule_quality_lookback_days,
)
from ezrules.core.audit_helpers import save_outcome_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import RuleFactory
from ezrules.core.rule_checkers import AllowedOutcomeReturnVisitor
from ezrules.core.rule_updater import RULE_EVALUATION_LANE_ALLOWLIST
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Action, AllowedOutcome, Label, RoleActions, RuleQualityPair, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/settings", tags=["Settings"])


def _serialize_rule_quality_pair(pair: RuleQualityPair) -> RuleQualityPairResponse:
    return RuleQualityPairResponse(
        rqp_id=int(pair.rqp_id),
        outcome=str(pair.outcome),
        label=str(pair.label),
        active=bool(pair.active),
        created_at=cast(datetime, pair.created_at),
        updated_at=cast(datetime, pair.updated_at),
        created_by=cast(str | None, pair.created_by),
    )


def _list_outcomes_in_severity_order(db: Any, org_id: int) -> list[AllowedOutcome]:
    return (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == org_id)
        .order_by(AllowedOutcome.severity_rank.asc(), AllowedOutcome.outcome_name.asc())
        .all()
    )


def _serialize_outcome(outcome: AllowedOutcome) -> OutcomeHierarchyItem:
    return OutcomeHierarchyItem(
        ao_id=int(outcome.ao_id),
        outcome_name=str(outcome.outcome_name),
        severity_rank=int(outcome.severity_rank),
    )


def _validate_allowlist_rule(
    rule: RuleModel, neutral_outcome: str, list_provider: PersistentUserListManager
) -> str | None:
    try:
        compiled_rule = RuleFactory.from_json(
            {
                "rid": str(rule.rid),
                "logic": str(rule.logic),
                "description": str(rule.description),
            },
            list_values_provider=list_provider,
        )
    except Exception as exc:
        return f"Rule could not be revalidated: {exc!s}"

    visitor = AllowedOutcomeReturnVisitor()
    visitor.visit(compiled_rule._rule_ast)
    if not visitor.values:
        return f"Allowlist rules must contain at least one return !{neutral_outcome} statement."

    invalid_values = [value for value in visitor.values if value != neutral_outcome]
    if invalid_values:
        rendered_values = ", ".join(sorted({repr(value) for value in invalid_values}))
        return f"Allowlist rules must return only the configured neutral outcome !{neutral_outcome}. Found {rendered_values}."
    return None


def _list_invalid_allowlist_rules(db: Any, org_id: int, neutral_outcome: str) -> list[InvalidAllowlistRule]:
    rules = (
        db.query(RuleModel)
        .filter(RuleModel.o_id == org_id, RuleModel.evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST)
        .order_by(RuleModel.r_id.asc())
        .all()
    )
    list_provider = PersistentUserListManager(db_session=db, o_id=org_id)
    invalid_rules: list[InvalidAllowlistRule] = []
    for rule in rules:
        error = _validate_allowlist_rule(rule, neutral_outcome, list_provider)
        if error is None:
            continue
        invalid_rules.append(
            InvalidAllowlistRule(
                r_id=int(rule.r_id),
                rid=str(rule.rid),
                description=str(rule.description),
                error=error,
            )
        )
    return invalid_rules


def _validate_neutral_outcome(db: Any, org_id: int, value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="neutral_outcome cannot be empty")

    exists = (
        db.query(AllowedOutcome.ao_id)
        .filter(AllowedOutcome.o_id == org_id, func.upper(AllowedOutcome.outcome_name) == normalized)
        .first()
        is not None
    )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Neutral outcome must match an existing configured outcome",
        )

    return normalized


def _user_has_permission(db: Any, user: User, action: PermissionAction) -> bool:
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


@router.get("/runtime", response_model=RuntimeSettingsResponse)
def get_runtime_settings(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuntimeSettingsResponse:
    """Return current runtime settings that can be tuned without redeploying."""
    return RuntimeSettingsResponse(
        auto_promote_active_rule_updates=get_auto_promote_active_rule_updates(db, current_org_id),
        default_auto_promote_active_rule_updates=AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
        main_rule_execution_mode=get_main_rule_execution_mode(db, current_org_id),
        default_main_rule_execution_mode=MAIN_RULE_EXECUTION_MODE_DEFAULT,
        rule_quality_lookback_days=get_rule_quality_lookback_days(db, current_org_id),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        neutral_outcome=get_neutral_outcome(db, current_org_id),
        default_neutral_outcome=NEUTRAL_OUTCOME_DEFAULT,
        invalid_allowlist_rules=_list_invalid_allowlist_rules(
            db, current_org_id, get_neutral_outcome(db, current_org_id)
        ),
    )


@router.put("/runtime", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    request_data: RuntimeSettingsUpdateRequest,
    user: User = Depends(get_current_active_user),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuntimeSettingsResponse:
    """Update runtime settings values."""
    updates_requested = (
        request_data.rule_quality_lookback_days is not None
        or request_data.auto_promote_active_rule_updates is not None
        or request_data.main_rule_execution_mode is not None
        or request_data.neutral_outcome is not None
    )
    if not updates_requested:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No runtime setting changes requested")

    if (
        request_data.rule_quality_lookback_days is not None
        or request_data.auto_promote_active_rule_updates is not None
        or request_data.main_rule_execution_mode is not None
    ) and not _user_has_permission(db, user, PermissionAction.MANAGE_PERMISSIONS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MANAGE_PERMISSIONS permission is required to update runtime settings",
        )

    if request_data.rule_quality_lookback_days is not None:
        set_rule_quality_lookback_days(db, request_data.rule_quality_lookback_days, current_org_id)
    if request_data.auto_promote_active_rule_updates is not None:
        set_auto_promote_active_rule_updates(db, request_data.auto_promote_active_rule_updates, current_org_id)
    if request_data.main_rule_execution_mode is not None:
        set_main_rule_execution_mode(db, request_data.main_rule_execution_mode, current_org_id)
    if request_data.neutral_outcome is not None:
        if not _user_has_permission(db, user, PermissionAction.MANAGE_NEUTRAL_OUTCOME):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MANAGE_NEUTRAL_OUTCOME permission is required to update the neutral outcome",
            )
        previous_neutral_outcome = get_neutral_outcome(db, current_org_id)
        next_neutral_outcome = _validate_neutral_outcome(db, current_org_id, request_data.neutral_outcome)
        set_neutral_outcome(db, next_neutral_outcome, current_org_id)
        if next_neutral_outcome != previous_neutral_outcome:
            save_outcome_history(
                db,
                ao_id=0,
                outcome_name=next_neutral_outcome,
                action="neutral_outcome_updated",
                o_id=current_org_id,
                changed_by=str(user.email) if user.email else None,
            )
    db.commit()

    neutral_outcome = get_neutral_outcome(db, current_org_id)
    return RuntimeSettingsResponse(
        auto_promote_active_rule_updates=get_auto_promote_active_rule_updates(db, current_org_id),
        default_auto_promote_active_rule_updates=AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
        main_rule_execution_mode=get_main_rule_execution_mode(db, current_org_id),
        default_main_rule_execution_mode=MAIN_RULE_EXECUTION_MODE_DEFAULT,
        rule_quality_lookback_days=get_rule_quality_lookback_days(db, current_org_id),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        neutral_outcome=neutral_outcome,
        default_neutral_outcome=NEUTRAL_OUTCOME_DEFAULT,
        invalid_allowlist_rules=_list_invalid_allowlist_rules(db, current_org_id, neutral_outcome),
    )


@router.get("/outcome-hierarchy", response_model=OutcomeHierarchyResponse)
def get_outcome_hierarchy(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> OutcomeHierarchyResponse:
    """Return the configured outcome severity ordering used for conflict resolution."""
    return OutcomeHierarchyResponse(
        outcomes=[_serialize_outcome(outcome) for outcome in _list_outcomes_in_severity_order(db, current_org_id)],
    )


@router.put("/outcome-hierarchy", response_model=OutcomeHierarchyResponse)
def update_outcome_hierarchy(
    request_data: OutcomeHierarchyUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> OutcomeHierarchyResponse:
    """Replace the full ordered outcome hierarchy for the current organization."""
    outcomes = _list_outcomes_in_severity_order(db, current_org_id)
    current_ids = [int(outcome.ao_id) for outcome in outcomes]
    requested_ids = [int(ao_id) for ao_id in request_data.ordered_ao_ids]

    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outcome hierarchy contains duplicate IDs")

    if requested_ids != current_ids and sorted(requested_ids) != sorted(current_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outcome hierarchy update must include every existing outcome exactly once",
        )

    by_id = {int(outcome.ao_id): outcome for outcome in outcomes}
    original_ranks = {int(outcome.ao_id): int(outcome.severity_rank) for outcome in outcomes}
    temporary_rank_base = len(requested_ids) + 100

    for temporary_offset, ao_id in enumerate(requested_ids, start=1):
        by_id[ao_id].severity_rank = temporary_rank_base + temporary_offset

    db.flush()

    for severity_rank, ao_id in enumerate(requested_ids, start=1):
        by_id[ao_id].severity_rank = severity_rank

    changed_outcomes = [
        by_id[ao_id]
        for severity_rank, ao_id in enumerate(requested_ids, start=1)
        if original_ranks[ao_id] != severity_rank
    ]

    for outcome in changed_outcomes:
        save_outcome_history(
            db,
            ao_id=int(outcome.ao_id),
            outcome_name=str(outcome.outcome_name),
            action="reordered",
            o_id=current_org_id,
            changed_by=str(user.email) if user.email else None,
        )

    db.commit()
    return OutcomeHierarchyResponse(
        outcomes=[_serialize_outcome(outcome) for outcome in _list_outcomes_in_severity_order(db, current_org_id)],
    )


@router.get("/rule-quality-pairs", response_model=RuleQualityPairsListResponse)
def list_rule_quality_pairs(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityPairsListResponse:
    pairs = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.o_id == current_org_id)
        .order_by(RuleQualityPair.outcome.asc(), RuleQualityPair.label.asc())
        .all()
    )
    return RuleQualityPairsListResponse(
        pairs=[_serialize_rule_quality_pair(pair) for pair in pairs],
    )


@router.get("/rule-quality-pairs/options", response_model=RuleQualityPairOptionsResponse)
def get_rule_quality_pair_options(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityPairOptionsResponse:
    outcomes = [
        str(item.outcome_name)
        for item in db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == current_org_id)
        .order_by(AllowedOutcome.severity_rank.asc(), AllowedOutcome.outcome_name.asc())
        .all()
    ]
    labels = [
        str(item.label)
        for item in db.query(Label).filter(Label.o_id == current_org_id).order_by(Label.label.asc()).all()
    ]
    return RuleQualityPairOptionsResponse(
        outcomes=outcomes,
        labels=labels,
    )


@router.post("/rule-quality-pairs", response_model=RuleQualityPairResponse)
def create_rule_quality_pair(
    request_data: RuleQualityPairCreateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityPairResponse:
    outcome = request_data.outcome.strip()
    label = request_data.label.strip()

    outcome_exists = (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == current_org_id)
        .filter(AllowedOutcome.outcome_name == outcome)
        .first()
        is not None
    )
    if not outcome_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown outcome '{outcome}'",
        )

    label_exists = (
        db.query(Label)
        .filter(
            Label.o_id == current_org_id,
            func.upper(Label.label) == label.upper(),
        )
        .first()
        is not None
    )
    if not label_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown label '{label}'",
        )

    existing = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.o_id == current_org_id)
        .filter(RuleQualityPair.outcome == outcome)
        .filter(RuleQualityPair.label == label)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pair '{outcome} -> {label}' already exists",
        )

    pair = RuleQualityPair(
        outcome=outcome,
        label=label,
        active=True,
        created_by=str(user.email),
        o_id=current_org_id,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return _serialize_rule_quality_pair(pair)


@router.put("/rule-quality-pairs/{pair_id}", response_model=RuleQualityPairResponse)
def update_rule_quality_pair(
    pair_id: int,
    request_data: RuleQualityPairUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityPairResponse:
    pair = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.rqp_id == pair_id)
        .filter(RuleQualityPair.o_id == current_org_id)
        .first()
    )
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule quality pair not found")

    pair.active = request_data.active
    db.commit()
    db.refresh(pair)
    return _serialize_rule_quality_pair(pair)


@router.delete("/rule-quality-pairs/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule_quality_pair(
    pair_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> Response:
    pair = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.rqp_id == pair_id)
        .filter(RuleQualityPair.o_id == current_org_id)
        .first()
    )
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule quality pair not found")

    db.delete(pair)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
