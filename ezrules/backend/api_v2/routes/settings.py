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
    ALLOWLIST_MATCH_OUTCOME_DEFAULT,
    AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
    get_allowlist_match_outcome,
    get_auto_promote_active_rule_updates,
    get_rule_quality_lookback_days,
    set_allowlist_match_outcome,
    set_auto_promote_active_rule_updates,
    set_rule_quality_lookback_days,
)
from ezrules.core.audit_helpers import save_outcome_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AllowedOutcome, Label, RuleQualityPair, User
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
        rule_quality_lookback_days=get_rule_quality_lookback_days(db, current_org_id),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        allowlist_match_outcome=get_allowlist_match_outcome(db, current_org_id),
        default_allowlist_match_outcome=ALLOWLIST_MATCH_OUTCOME_DEFAULT,
    )


@router.put("/runtime", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    request_data: RuntimeSettingsUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuntimeSettingsResponse:
    """Update runtime settings values."""
    set_rule_quality_lookback_days(db, request_data.rule_quality_lookback_days, current_org_id)
    if request_data.auto_promote_active_rule_updates is not None:
        set_auto_promote_active_rule_updates(db, request_data.auto_promote_active_rule_updates, current_org_id)
    if request_data.allowlist_match_outcome is not None:
        set_allowlist_match_outcome(db, request_data.allowlist_match_outcome, current_org_id)
    db.commit()

    return RuntimeSettingsResponse(
        auto_promote_active_rule_updates=get_auto_promote_active_rule_updates(db, current_org_id),
        default_auto_promote_active_rule_updates=AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
        rule_quality_lookback_days=get_rule_quality_lookback_days(db, current_org_id),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        allowlist_match_outcome=get_allowlist_match_outcome(db, current_org_id),
        default_allowlist_match_outcome=ALLOWLIST_MATCH_OUTCOME_DEFAULT,
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
