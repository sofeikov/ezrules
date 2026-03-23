"""
FastAPI routes for shadow deployment overview and results.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
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


def _load_shadow_entries(db: Any, current_org_id: int) -> list[dict[str, Any]]:
    new_rows = (
        db.query(RuleDeploymentResultsLog, TestingRecordLog)
        .join(TestingRecordLog, RuleDeploymentResultsLog.tl_id == TestingRecordLog.tl_id)
        .filter(
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "shadow",
        )
        .all()
    )

    entries = [
        {
            "log_id": int(log.dr_id),
            "tl_id": int(log.tl_id),
            "r_id": int(log.r_id),
            "shadow_result": str(log.candidate_result) if log.candidate_result is not None else "None",
            "prod_result": str(log.control_result) if log.control_result is not None else "None",
            "event_id": str(tl.event_id),
            "event_timestamp": int(tl.event_timestamp),
            "created_at": log.created_at,
        }
        for log, tl in new_rows
    ]

    existing_pairs = {(entry["tl_id"], entry["r_id"]) for entry in entries}

    legacy_rows = (
        db.query(ShadowResultsLog, TestingRecordLog, TestingResultsLog.rule_result)
        .join(TestingRecordLog, ShadowResultsLog.tl_id == TestingRecordLog.tl_id)
        .outerjoin(
            TestingResultsLog,
            (TestingResultsLog.tl_id == ShadowResultsLog.tl_id) & (TestingResultsLog.r_id == ShadowResultsLog.r_id),
        )
        .filter(TestingRecordLog.o_id == current_org_id)
        .all()
    )

    for shadow_log, tl, prod_result in legacy_rows:
        pair = (int(shadow_log.tl_id), int(shadow_log.r_id))
        if pair in existing_pairs:
            continue
        entries.append(
            {
                "log_id": int(shadow_log.sr_id),
                "tl_id": int(shadow_log.tl_id),
                "r_id": int(shadow_log.r_id),
                "shadow_result": str(shadow_log.rule_result),
                "prod_result": str(prod_result) if prod_result is not None else "None",
                "event_id": str(tl.event_id),
                "event_timestamp": int(tl.event_timestamp),
                "created_at": shadow_log.created_at,
            }
        )

    return entries


def _sort_shadow_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(entry: dict[str, Any]) -> tuple[datetime, int]:
        created_at = entry["created_at"] or datetime.min.replace(tzinfo=UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return (created_at, entry["log_id"])

    return sorted(entries, key=sort_key, reverse=True)


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
    entries = _sort_shadow_entries(_load_shadow_entries(db, current_org_id))
    total = len(entries)

    results = [
        ShadowResultItem(
            sr_id=int(entry["log_id"]),
            tl_id=int(entry["tl_id"]),
            r_id=int(entry["r_id"]),
            rule_result=str(entry["shadow_result"]),
            event_id=str(entry["event_id"]),
            event_timestamp=int(entry["event_timestamp"]),
            created_at=entry["created_at"],
        )
        for entry in entries[:limit]
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
    shadow_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    prod_by_rule: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for entry in _load_shadow_entries(db, current_org_id):
        r_id = int(entry["r_id"])
        shadow_by_rule[r_id][str(entry["shadow_result"])] += 1
        prod_by_rule[r_id][str(entry["prod_result"])] += 1

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
