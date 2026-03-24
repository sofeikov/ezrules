"""
FastAPI routes for shadow deployment overview and results.
"""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, literal, select, union_all
from sqlalchemy.exc import NoResultFound

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
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
from ezrules.models.backend_core import (
    RuleDeploymentResultsLog,
    RuleEngineConfig,
    ShadowResultsLog,
    TestingRecordLog,
    TestingResultsLog,
    User,
)

router = APIRouter(prefix="/api/v2/shadow", tags=["Shadow"])


def _shadow_entries_subquery(current_org_id: int):
    new_entries = (
        select(
            RuleDeploymentResultsLog.dr_id.label("log_id"),
            RuleDeploymentResultsLog.tl_id.label("tl_id"),
            RuleDeploymentResultsLog.r_id.label("r_id"),
            func.coalesce(RuleDeploymentResultsLog.candidate_result, literal("None")).label("shadow_result"),
            func.coalesce(RuleDeploymentResultsLog.control_result, literal("None")).label("prod_result"),
            TestingRecordLog.event_id.label("event_id"),
            TestingRecordLog.event_timestamp.label("event_timestamp"),
            RuleDeploymentResultsLog.created_at.label("created_at"),
        )
        .join(TestingRecordLog, RuleDeploymentResultsLog.tl_id == TestingRecordLog.tl_id)
        .where(
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "shadow",
            TestingRecordLog.o_id == current_org_id,
        )
    )

    matching_shared_log_exists = exists(
        select(1).where(
            RuleDeploymentResultsLog.tl_id == ShadowResultsLog.tl_id,
            RuleDeploymentResultsLog.r_id == ShadowResultsLog.r_id,
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "shadow",
        )
    ).correlate(ShadowResultsLog)

    legacy_entries = (
        select(
            ShadowResultsLog.sr_id.label("log_id"),
            ShadowResultsLog.tl_id.label("tl_id"),
            ShadowResultsLog.r_id.label("r_id"),
            func.coalesce(ShadowResultsLog.rule_result, literal("None")).label("shadow_result"),
            func.coalesce(TestingResultsLog.rule_result, literal("None")).label("prod_result"),
            TestingRecordLog.event_id.label("event_id"),
            TestingRecordLog.event_timestamp.label("event_timestamp"),
            ShadowResultsLog.created_at.label("created_at"),
        )
        .join(TestingRecordLog, ShadowResultsLog.tl_id == TestingRecordLog.tl_id)
        .outerjoin(
            TestingResultsLog,
            (TestingResultsLog.tl_id == ShadowResultsLog.tl_id) & (TestingResultsLog.r_id == ShadowResultsLog.r_id),
        )
        .where(
            TestingRecordLog.o_id == current_org_id,
            ~matching_shared_log_exists,
        )
    )

    return union_all(new_entries, legacy_entries).subquery("shadow_entries")


@router.get("", response_model=ShadowConfigResponse)
def get_shadow_config(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowConfigResponse:
    """Return the current shadow config — which rules are in shadow and their versions."""
    try:
        config_obj = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "shadow",
                RuleEngineConfig.o_id == current_org_id,
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
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowResultsResponse:
    """Return recent shadow evaluation results joined with event metadata."""
    shadow_entries = _shadow_entries_subquery(current_org_id)
    rows = (
        db.query(
            shadow_entries.c.log_id,
            shadow_entries.c.tl_id,
            shadow_entries.c.r_id,
            shadow_entries.c.shadow_result,
            shadow_entries.c.event_id,
            shadow_entries.c.event_timestamp,
            shadow_entries.c.created_at,
        )
        .order_by(shadow_entries.c.created_at.desc(), shadow_entries.c.log_id.desc())
        .limit(limit)
        .all()
    )
    total = db.query(func.count()).select_from(shadow_entries).scalar() or 0

    results = [
        ShadowResultItem(
            sr_id=int(row.log_id),
            tl_id=int(row.tl_id),
            r_id=int(row.r_id),
            rule_result=str(row.shadow_result),
            event_id=str(row.event_id),
            event_timestamp=int(row.event_timestamp),
            created_at=row.created_at,
        )
        for row in rows
    ]

    return ShadowResultsResponse(results=results, total=total)


@router.get("/stats", response_model=ShadowStatsResponse)
def get_shadow_stats(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> ShadowStatsResponse:
    """Return shadow vs production outcome counts per rule for the same events."""
    shadow_entries = _shadow_entries_subquery(current_org_id)
    rows = (
        db.query(
            shadow_entries.c.r_id,
            shadow_entries.c.shadow_result,
            shadow_entries.c.prod_result,
            func.count().label("cnt"),
        )
        .group_by(
            shadow_entries.c.r_id,
            shadow_entries.c.shadow_result,
            shadow_entries.c.prod_result,
        )
        .all()
    )

    shadow_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    prod_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        r_id = int(row.r_id)
        shadow_by_rule[r_id][str(row.shadow_result)] += int(row.cnt)
        prod_by_rule[r_id][str(row.prod_result)] += int(row.cnt)

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
