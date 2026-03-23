"""
FastAPI routes for rollout deployment overview and results.
"""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.rollouts import (
    RolloutConfigResponse,
    RolloutOutcomeCount,
    RolloutResultItem,
    RolloutResultsResponse,
    RolloutRuleItem,
    RolloutRuleStatsItem,
    RolloutStatsResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import ROLLOUT_CONFIG_LABEL, get_deployment_config, list_candidate_deployments
from ezrules.models.backend_core import RuleDeploymentResultsLog, TestingRecordLog, User

router = APIRouter(prefix="/api/v2/rollouts", tags=["Rollouts"])


@router.get("", response_model=RolloutConfigResponse)
def get_rollout_config(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutConfigResponse:
    config_obj = get_deployment_config(db, o_id=current_org_id, label=ROLLOUT_CONFIG_LABEL)
    if config_obj is None:
        return RolloutConfigResponse(rules=[], version=0)

    rules = [
        RolloutRuleItem(
            r_id=int(entry["r_id"]),
            rid=str(entry["rid"]),
            description=str(entry["description"]),
            logic=str(entry["logic"]),
            traffic_percent=int(entry.get("traffic_percent") or 0),
        )
        for entry in config_obj.config
    ]
    return RolloutConfigResponse(rules=rules, version=int(config_obj.version))


@router.get("/results", response_model=RolloutResultsResponse)
def get_rollout_results(
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutResultsResponse:
    rows = (
        db.query(RuleDeploymentResultsLog, TestingRecordLog)
        .join(TestingRecordLog, RuleDeploymentResultsLog.tl_id == TestingRecordLog.tl_id)
        .filter(
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "split",
        )
        .order_by(RuleDeploymentResultsLog.dr_id.desc())
        .limit(limit)
        .all()
    )

    total = (
        db.query(RuleDeploymentResultsLog)
        .filter(
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "split",
        )
        .count()
    )

    results = [
        RolloutResultItem(
            dr_id=int(log.dr_id),
            tl_id=int(log.tl_id),
            r_id=int(log.r_id),
            selected_variant=str(log.selected_variant),
            traffic_percent=int(log.traffic_percent) if log.traffic_percent is not None else None,
            bucket=int(log.bucket) if log.bucket is not None else None,
            control_result=str(log.control_result) if log.control_result is not None else None,
            candidate_result=str(log.candidate_result) if log.candidate_result is not None else None,
            returned_result=str(log.returned_result) if log.returned_result is not None else None,
            event_id=str(record.event_id),
            event_timestamp=int(record.event_timestamp),
            created_at=log.created_at,
        )
        for log, record in rows
    ]
    return RolloutResultsResponse(results=results, total=total)


@router.get("/stats", response_model=RolloutStatsResponse)
def get_rollout_stats(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RolloutStatsResponse:
    rollout_entries = {
        int(entry["r_id"]): entry for entry in list_candidate_deployments(db, current_org_id, ROLLOUT_CONFIG_LABEL)
    }
    logs = (
        db.query(RuleDeploymentResultsLog)
        .filter(
            RuleDeploymentResultsLog.o_id == current_org_id,
            RuleDeploymentResultsLog.mode == "split",
        )
        .all()
    )

    candidate_outcomes: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    control_outcomes: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    served_candidate: dict[int, int] = defaultdict(int)
    served_control: dict[int, int] = defaultdict(int)
    total_by_rule: dict[int, int] = defaultdict(int)

    for log in logs:
        r_id = int(log.r_id)
        total_by_rule[r_id] += 1
        candidate_outcomes[r_id][str(log.candidate_result) if log.candidate_result is not None else "None"] += 1
        control_outcomes[r_id][str(log.control_result) if log.control_result is not None else "None"] += 1
        if log.selected_variant == "candidate":
            served_candidate[r_id] += 1
        else:
            served_control[r_id] += 1

    def sorted_outcomes(counts: dict[str, int]) -> list[RolloutOutcomeCount]:
        return sorted(
            [RolloutOutcomeCount(outcome=outcome, count=count) for outcome, count in counts.items()],
            key=lambda x: -x.count,
        )

    rules = [
        RolloutRuleStatsItem(
            r_id=r_id,
            traffic_percent=int(entry.get("traffic_percent") or 0),
            total=int(total_by_rule.get(r_id, 0)),
            served_candidate=int(served_candidate.get(r_id, 0)),
            served_control=int(served_control.get(r_id, 0)),
            candidate_outcomes=sorted_outcomes(dict(candidate_outcomes.get(r_id, {}))),
            control_outcomes=sorted_outcomes(dict(control_outcomes.get(r_id, {}))),
        )
        for r_id, entry in rollout_entries.items()
    ]
    return RolloutStatsResponse(rules=rules)
