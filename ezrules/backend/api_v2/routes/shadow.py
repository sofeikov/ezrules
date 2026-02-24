"""
FastAPI routes for shadow deployment overview and results.
"""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.exc import NoResultFound

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.shadow import (
    ShadowConfigResponse,
    ShadowOutcomeCount,
    ShadowResultItem,
    ShadowResultsResponse,
    ShadowRuleItem,
    ShadowRuleStatsItem,
    ShadowStatsResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import RuleEngineConfig, ShadowResultsLog, TestingRecordLog, TestingResultsLog, User
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/shadow", tags=["Shadow"])


@router.get("", response_model=ShadowConfigResponse)
def get_shadow_config(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> ShadowConfigResponse:
    """Return the current shadow config — which rules are in shadow and their versions."""
    try:
        config_obj = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "shadow",
                RuleEngineConfig.o_id == app_settings.ORG_ID,
            )
            .one()
        )
    except NoResultFound:
        return ShadowConfigResponse(rules=[], version=0)

    rules = [
        ShadowRuleItem(
            r_id=int(r["r_id"]),
            rid=str(r["rid"]),
            description=str(r["description"]),
            logic=str(r["logic"]),
        )
        for r in config_obj.config
    ]
    return ShadowConfigResponse(rules=rules, version=int(config_obj.version))


@router.get("/results", response_model=ShadowResultsResponse)
def get_shadow_results(
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> ShadowResultsResponse:
    """Return recent shadow evaluation results joined with event metadata."""
    rows = (
        db.query(ShadowResultsLog, TestingRecordLog)
        .join(TestingRecordLog, ShadowResultsLog.tl_id == TestingRecordLog.tl_id)
        .order_by(ShadowResultsLog.sr_id.desc())
        .limit(limit)
        .all()
    )

    total = db.query(ShadowResultsLog).count()

    results = [
        ShadowResultItem(
            sr_id=int(sr.sr_id),
            tl_id=int(sr.tl_id),
            r_id=int(sr.r_id),
            rule_result=str(sr.rule_result),
            event_id=str(tl.event_id),
            event_timestamp=int(tl.event_timestamp),
            created_at=sr.created_at,
        )
        for sr, tl in rows
    ]

    return ShadowResultsResponse(results=results, total=total)


@router.get("/stats", response_model=ShadowStatsResponse)
def get_shadow_stats(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> ShadowStatsResponse:
    """Return shadow vs production outcome counts per rule for the same events."""
    # LEFT JOIN so we get production result = None when the production rule didn't fire
    rows = (
        db.query(
            ShadowResultsLog.r_id,
            ShadowResultsLog.rule_result.label("shadow_result"),
            func.coalesce(TestingResultsLog.rule_result, "None").label("prod_result"),
            func.count().label("cnt"),
        )
        .outerjoin(
            TestingResultsLog,
            (ShadowResultsLog.tl_id == TestingResultsLog.tl_id) & (ShadowResultsLog.r_id == TestingResultsLog.r_id),
        )
        .group_by(
            ShadowResultsLog.r_id,
            ShadowResultsLog.rule_result,
            func.coalesce(TestingResultsLog.rule_result, "None"),
        )
        .all()
    )

    shadow_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    prod_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r_id, shadow_result, prod_result, cnt in rows:
        shadow_by_rule[int(r_id)][str(shadow_result)] += int(cnt)
        prod_by_rule[int(r_id)][str(prod_result)] += int(cnt)

    all_r_ids = set(shadow_by_rule) | set(prod_by_rule)

    def sorted_outcomes(counts: dict[str, int]) -> list[ShadowOutcomeCount]:
        return sorted([ShadowOutcomeCount(outcome=o, count=c) for o, c in counts.items()], key=lambda x: -x.count)

    rule_stats = [
        ShadowRuleStatsItem(
            r_id=r_id,
            total=sum(shadow_by_rule[r_id].values()),
            shadow_outcomes=sorted_outcomes(dict(shadow_by_rule[r_id])),
            prod_outcomes=sorted_outcomes(dict(prod_by_rule[r_id])),
        )
        for r_id in all_r_ids
    ]

    return ShadowStatsResponse(rules=rule_stats)
