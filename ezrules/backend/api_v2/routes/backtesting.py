from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.backtesting import (
    BacktestRequest,
    BacktestResultItem,
    BacktestResultsResponse,
    BacktestTaskResult,
    BacktestTriggerResponse,
)
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import RuleBackTestingResult, User

router = APIRouter(prefix="/api/v2/backtesting", tags=["Backtesting"])


@router.post("", response_model=BacktestTriggerResponse)
def trigger_backtest(
    request: BacktestRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    db: Any = Depends(get_db),
) -> BacktestTriggerResponse:
    rule = db.get(RuleModel, request.r_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    try:
        Rule(rid="", logic=request.new_rule_logic)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid proposed rule logic: {e!s}",
        ) from e

    task = backtest_rule_change.delay(request.r_id, request.new_rule_logic)

    bt_result = RuleBackTestingResult(
        r_id=request.r_id,
        task_id=task.id,
        stored_logic=rule.logic,
        proposed_logic=request.new_rule_logic,
    )
    db.add(bt_result)
    db.commit()

    return BacktestTriggerResponse(
        success=True,
        task_id=task.id,
        message="Backtest started",
    )


@router.get("/task/{task_id}", response_model=BacktestTaskResult)
def get_task_result(
    task_id: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
) -> BacktestTaskResult:
    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING":
        return BacktestTaskResult(status="PENDING")

    if result.state == "FAILURE":
        return BacktestTaskResult(status="FAILURE", error=str(result.result))

    if result.state == "SUCCESS":
        data = result.result
        if isinstance(data, dict) and "error" in data:
            return BacktestTaskResult(status="FAILURE", error=data["error"])
        return BacktestTaskResult(
            status="SUCCESS",
            stored_result=data.get("stored_result"),
            proposed_result=data.get("proposed_result"),
            stored_result_rate=data.get("stored_result_rate"),
            proposed_result_rate=data.get("proposed_result_rate"),
            total_records=data.get("total_records"),
        )

    return BacktestTaskResult(status=result.state)


@router.get("/{rule_id}", response_model=BacktestResultsResponse)
def get_backtest_results(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> BacktestResultsResponse:
    results = (
        db.query(RuleBackTestingResult)
        .filter(RuleBackTestingResult.r_id == rule_id)
        .order_by(RuleBackTestingResult.created_at.desc())
        .limit(3)
        .all()
    )

    items = [
        BacktestResultItem(
            task_id=str(r.task_id),
            created_at=r.created_at,
            stored_logic=r.stored_logic,
            proposed_logic=r.proposed_logic,
        )
        for r in results
    ]

    return BacktestResultsResponse(results=items)
