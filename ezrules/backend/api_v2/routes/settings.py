"""FastAPI routes for runtime settings and rule-quality pair catalog management."""

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ezrules.backend.api_v2.auth.dependencies import get_current_active_user, get_db, require_permission
from ezrules.backend.api_v2.schemas.settings import (
    RuleQualityPairCreateRequest,
    RuleQualityPairOptionsResponse,
    RuleQualityPairResponse,
    RuleQualityPairsListResponse,
    RuleQualityPairUpdateRequest,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from ezrules.backend.runtime_settings import (
    get_rule_quality_lookback_days,
    set_rule_quality_lookback_days,
)
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


@router.get("/runtime", response_model=RuntimeSettingsResponse)
def get_runtime_settings(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> RuntimeSettingsResponse:
    """Return current runtime settings that can be tuned without redeploying."""
    return RuntimeSettingsResponse(
        rule_quality_lookback_days=get_rule_quality_lookback_days(db),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
    )


@router.put("/runtime", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    request_data: RuntimeSettingsUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    db: Any = Depends(get_db),
) -> RuntimeSettingsResponse:
    """Update runtime settings values."""
    set_rule_quality_lookback_days(db, request_data.rule_quality_lookback_days)
    db.commit()

    return RuntimeSettingsResponse(
        rule_quality_lookback_days=get_rule_quality_lookback_days(db),
        default_rule_quality_lookback_days=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
    )


@router.get("/rule-quality-pairs", response_model=RuleQualityPairsListResponse)
def list_rule_quality_pairs(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> RuleQualityPairsListResponse:
    pairs = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.o_id == app_settings.ORG_ID)
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
    db: Any = Depends(get_db),
) -> RuleQualityPairOptionsResponse:
    outcomes = [
        str(item.outcome_name)
        for item in db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == app_settings.ORG_ID)
        .order_by(AllowedOutcome.outcome_name.asc())
        .all()
    ]
    labels = [str(item.label) for item in db.query(Label).order_by(Label.label.asc()).all()]
    return RuleQualityPairOptionsResponse(
        outcomes=outcomes,
        labels=labels,
    )


@router.post("/rule-quality-pairs", response_model=RuleQualityPairResponse)
def create_rule_quality_pair(
    request_data: RuleQualityPairCreateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    db: Any = Depends(get_db),
) -> RuleQualityPairResponse:
    outcome = request_data.outcome.strip()
    label = request_data.label.strip()

    outcome_exists = (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == app_settings.ORG_ID)
        .filter(AllowedOutcome.outcome_name == outcome)
        .first()
        is not None
    )
    if not outcome_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown outcome '{outcome}'",
        )

    label_exists = db.query(Label).filter(Label.label == label).first() is not None
    if not label_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown label '{label}'",
        )

    existing = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.o_id == app_settings.ORG_ID)
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
        o_id=app_settings.ORG_ID,
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
    db: Any = Depends(get_db),
) -> RuleQualityPairResponse:
    pair = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.rqp_id == pair_id)
        .filter(RuleQualityPair.o_id == app_settings.ORG_ID)
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
    db: Any = Depends(get_db),
) -> Response:
    pair = (
        db.query(RuleQualityPair)
        .filter(RuleQualityPair.rqp_id == pair_id)
        .filter(RuleQualityPair.o_id == app_settings.ORG_ID)
        .first()
    )
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule quality pair not found")

    db.delete(pair)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
