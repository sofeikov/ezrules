from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
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
from ezrules.backend.backtesting import (
    ACTIVE_BACKTEST_QUEUE_STATUSES,
    BACKTEST_QUEUE_CANCELLED,
    BACKTEST_QUEUE_DONE,
    BACKTEST_QUEUE_FAILED,
    BACKTEST_QUEUE_PENDING,
    BACKTEST_QUEUE_RUNNING,
)
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change, execute_backtest_rule_change
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import RuleBackTestingResult, User

router = APIRouter(prefix="/api/v2/backtesting", tags=["Backtesting"])
_MAX_EAGER_BACKTEST_RESULTS = 128
_EAGER_BACKTEST_RESULTS: OrderedDict[str, dict[str, Any]] = OrderedDict()
_SYNC_BACKTEST_FALLBACK_DELAY = timedelta(seconds=2)


def _queue_status_to_response_status(queue_status: str) -> str:
    if queue_status == BACKTEST_QUEUE_DONE:
        return "SUCCESS"
    if queue_status == BACKTEST_QUEUE_FAILED:
        return "FAILURE"
    if queue_status == BACKTEST_QUEUE_CANCELLED:
        return "CANCELLED"
    return "PENDING"


def _build_task_result_response(
    *,
    queue_status: str,
    data: dict[str, Any] | None = None,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> BacktestTaskResult:
    payload = data if isinstance(data, dict) else {}
    return BacktestTaskResult(
        status=_queue_status_to_response_status(queue_status),
        queue_status=queue_status,
        created_at=created_at,
        completed_at=completed_at,
        stored_result=payload.get("stored_result"),
        proposed_result=payload.get("proposed_result"),
        stored_result_rate=payload.get("stored_result_rate"),
        proposed_result_rate=payload.get("proposed_result_rate"),
        total_records=payload.get("total_records"),
        eligible_records=payload.get("eligible_records"),
        skipped_records=payload.get("skipped_records"),
        labeled_records=payload.get("labeled_records"),
        label_counts=payload.get("label_counts"),
        stored_quality_summary=payload.get("stored_quality_summary"),
        proposed_quality_summary=payload.get("proposed_quality_summary"),
        stored_quality_metrics=payload.get("stored_quality_metrics"),
        proposed_quality_metrics=payload.get("proposed_quality_metrics"),
        warnings=payload.get("warnings"),
        error=(
            str(payload["error"])
            if "error" in payload
            else "Backtest cancelled by operator"
            if queue_status == BACKTEST_QUEUE_CANCELLED
            else None
        ),
    )


def _store_eager_backtest_result(task_id: str, result: dict[str, Any]) -> None:
    _EAGER_BACKTEST_RESULTS[task_id] = result
    _EAGER_BACKTEST_RESULTS.move_to_end(task_id)
    while len(_EAGER_BACKTEST_RESULTS) > _MAX_EAGER_BACKTEST_RESULTS:
        _EAGER_BACKTEST_RESULTS.popitem(last=False)


def _record_queue_status(task_record: RuleBackTestingResult) -> str:
    return str(task_record.status or BACKTEST_QUEUE_PENDING)


def _record_result_metrics(task_record: RuleBackTestingResult) -> dict[str, Any] | None:
    payload = task_record.result_metrics
    return payload if isinstance(payload, dict) else None


def _record_datetime(value: Any) -> datetime | None:
    record_datetime = cast(datetime | None, value)
    if record_datetime is None:
        return None
    if record_datetime.tzinfo is None:
        return record_datetime.replace(tzinfo=UTC)
    return record_datetime


def _persist_record_from_async_result(task_record: RuleBackTestingResult, db: Any) -> RuleBackTestingResult:
    if _record_queue_status(task_record) == BACKTEST_QUEUE_CANCELLED:
        return task_record

    eager_result = _EAGER_BACKTEST_RESULTS.get(str(task_record.task_id))
    if eager_result is not None:
        task_record.status = BACKTEST_QUEUE_DONE
        task_record.result_metrics = eager_result
        task_record.completed_at = task_record.completed_at or datetime.now(UTC)
        db.commit()
        db.refresh(task_record)
        return task_record

    async_result = AsyncResult(str(task_record.task_id), app=celery_app)
    payload: dict[str, Any] | None = None
    next_status: str | None = None

    if async_result.state == "SUCCESS":
        if isinstance(async_result.result, dict):
            payload = async_result.result
            next_status = BACKTEST_QUEUE_DONE
        else:
            payload = {"error": "Backtest task returned an invalid result payload"}
            next_status = BACKTEST_QUEUE_FAILED
    elif async_result.state == "FAILURE":
        payload = {"error": str(async_result.result)}
        next_status = BACKTEST_QUEUE_FAILED
    elif async_result.state == "REVOKED":
        payload = {"error": "Backtest cancelled by operator"}
        next_status = BACKTEST_QUEUE_CANCELLED
    elif async_result.state in {"STARTED", "RETRY"}:
        next_status = BACKTEST_QUEUE_RUNNING

    if next_status is None:
        return task_record

    task_record.status = next_status
    if payload is not None:
        task_record.result_metrics = payload
    if next_status in {BACKTEST_QUEUE_DONE, BACKTEST_QUEUE_FAILED, BACKTEST_QUEUE_CANCELLED}:
        task_record.completed_at = task_record.completed_at or datetime.now(UTC)
    db.commit()
    db.refresh(task_record)
    return task_record


def _should_run_sync_backtest_fallback(task_record: RuleBackTestingResult) -> bool:
    created_at = _record_datetime(task_record.created_at)
    if created_at is None:
        return False
    if _record_result_metrics(task_record) is not None:
        return False
    if _record_queue_status(task_record) != BACKTEST_QUEUE_PENDING:
        return False
    return datetime.now(UTC) - created_at.astimezone(UTC) >= _SYNC_BACKTEST_FALLBACK_DELAY


def _run_sync_backtest_fallback(task_record: RuleBackTestingResult, db: Any) -> RuleBackTestingResult:
    if not _should_run_sync_backtest_fallback(task_record):
        return task_record

    rule = cast(RuleModel | None, task_record.rule)
    if rule is None:
        return task_record

    execute_backtest_rule_change(
        int(task_record.r_id),
        cast(str, task_record.proposed_logic or rule.logic),
        int(rule.o_id),
        task_id=str(task_record.task_id),
    )
    db.refresh(task_record)
    return task_record


def _enqueue_backtest(rule_id: int, new_rule_logic: str, org_id: int, task_id: str) -> None:
    task = backtest_rule_change.apply_async(
        args=[rule_id, new_rule_logic, org_id],
        task_id=task_id,
    )
    if celery_app.conf.task_always_eager and task.id and isinstance(task.result, dict):
        _store_eager_backtest_result(str(task.id), task.result)


@router.post("", response_model=BacktestTriggerResponse)
def trigger_backtest(
    request: BacktestRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> BacktestTriggerResponse:
    rule = db.query(RuleModel).filter(RuleModel.r_id == request.r_id, RuleModel.o_id == current_org_id).first()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    try:
        Rule(
            rid="",
            logic=request.new_rule_logic,
            list_values_provider=PersistentUserListManager(db, current_org_id),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid proposed rule logic: {e!s}",
        ) from e

    task_id = str(uuid4())

    bt_result = RuleBackTestingResult(
        r_id=request.r_id,
        task_id=task_id,
        stored_logic=rule.logic,
        proposed_logic=request.new_rule_logic,
        status=BACKTEST_QUEUE_PENDING,
    )
    db.add(bt_result)
    db.commit()
    db.refresh(bt_result)

    try:
        _enqueue_backtest(request.r_id, request.new_rule_logic, current_org_id, task_id)
    except Exception as e:
        bt_result.status = BACKTEST_QUEUE_FAILED
        bt_result.result_metrics = {"error": f"Failed to queue backtest: {e!s}"}
        bt_result.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue backtest task",
        ) from e

    return BacktestTriggerResponse(
        success=True,
        task_id=task_id,
        message="Backtest started",
        queue_status=BACKTEST_QUEUE_PENDING,
    )


@router.get("/task/{task_id}", response_model=BacktestTaskResult)
def get_task_result(
    task_id: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> BacktestTaskResult:
    task_record = (
        db.query(RuleBackTestingResult)
        .join(RuleModel, RuleModel.r_id == RuleBackTestingResult.r_id)
        .filter(
            RuleBackTestingResult.task_id == task_id,
            RuleModel.o_id == current_org_id,
        )
        .first()
    )
    if task_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest task not found",
        )

    if (
        _record_result_metrics(task_record) is None
        or _record_queue_status(task_record) in ACTIVE_BACKTEST_QUEUE_STATUSES
    ):
        task_record = _persist_record_from_async_result(task_record, db)
        task_record = _run_sync_backtest_fallback(task_record, db)

    return _build_task_result_response(
        queue_status=_record_queue_status(task_record),
        data=_record_result_metrics(task_record),
        created_at=_record_datetime(task_record.created_at),
        completed_at=_record_datetime(task_record.completed_at),
    )


@router.delete("/{task_id}", response_model=BacktestTriggerResponse)
def cancel_backtest(
    task_id: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> BacktestTriggerResponse:
    task_record = (
        db.query(RuleBackTestingResult)
        .join(RuleModel, RuleModel.r_id == RuleBackTestingResult.r_id)
        .filter(
            RuleBackTestingResult.task_id == task_id,
            RuleModel.o_id == current_org_id,
        )
        .first()
    )
    if task_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest task not found",
        )

    if (
        _record_result_metrics(task_record) is None
        or _record_queue_status(task_record) in ACTIVE_BACKTEST_QUEUE_STATUSES
    ):
        task_record = _persist_record_from_async_result(task_record, db)

    if _record_queue_status(task_record) not in ACTIVE_BACKTEST_QUEUE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only queued or running backtests can be cancelled",
        )

    celery_app.control.revoke(task_id, terminate=True)
    task_record.status = BACKTEST_QUEUE_CANCELLED
    task_record.result_metrics = {"error": "Backtest cancelled by operator"}
    task_record.completed_at = datetime.now(UTC)
    db.commit()

    return BacktestTriggerResponse(
        success=True,
        task_id=task_id,
        message="Backtest cancelled",
        queue_status=BACKTEST_QUEUE_CANCELLED,
    )


@router.post("/{task_id}/retry", response_model=BacktestTriggerResponse)
def retry_backtest(
    task_id: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_RULE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> BacktestTriggerResponse:
    task_record = (
        db.query(RuleBackTestingResult)
        .join(RuleModel, RuleModel.r_id == RuleBackTestingResult.r_id)
        .filter(
            RuleBackTestingResult.task_id == task_id,
            RuleModel.o_id == current_org_id,
        )
        .first()
    )
    if task_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest task not found",
        )

    if (
        _record_result_metrics(task_record) is None
        or _record_queue_status(task_record) in ACTIVE_BACKTEST_QUEUE_STATUSES
    ):
        task_record = _persist_record_from_async_result(task_record, db)

    if _record_queue_status(task_record) not in {BACKTEST_QUEUE_FAILED, BACKTEST_QUEUE_CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or cancelled backtests can be retried",
        )

    retry_task_id = str(uuid4())
    retry_record = RuleBackTestingResult(
        r_id=task_record.r_id,
        task_id=retry_task_id,
        stored_logic=task_record.stored_logic,
        proposed_logic=task_record.proposed_logic,
        status=BACKTEST_QUEUE_PENDING,
    )
    db.add(retry_record)
    db.commit()
    db.refresh(retry_record)

    try:
        _enqueue_backtest(
            int(retry_record.r_id),
            str(retry_record.proposed_logic or ""),
            current_org_id,
            retry_task_id,
        )
    except Exception as e:
        retry_record.status = BACKTEST_QUEUE_FAILED
        retry_record.result_metrics = {"error": f"Failed to queue backtest retry: {e!s}"}
        retry_record.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue backtest retry",
        ) from e

    return BacktestTriggerResponse(
        success=True,
        task_id=retry_task_id,
        message="Backtest retried",
        queue_status=BACKTEST_QUEUE_PENDING,
    )


@router.get("/{rule_id}", response_model=BacktestResultsResponse)
def get_backtest_results(
    rule_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> BacktestResultsResponse:
    rule = db.query(RuleModel).filter(RuleModel.r_id == rule_id, RuleModel.o_id == current_org_id).first()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    results = (
        db.query(RuleBackTestingResult)
        .filter(RuleBackTestingResult.r_id == rule_id)
        .order_by(RuleBackTestingResult.created_at.desc())
        .limit(3)
        .all()
    )

    refreshed_results: list[RuleBackTestingResult] = []
    for result in results:
        if _record_result_metrics(result) is None or _record_queue_status(result) in ACTIVE_BACKTEST_QUEUE_STATUSES:
            result = _persist_record_from_async_result(result, db)
            result = _run_sync_backtest_fallback(result, db)
        refreshed_results.append(result)

    items = [
        BacktestResultItem(
            task_id=str(r.task_id),
            created_at=_record_datetime(r.created_at),
            completed_at=_record_datetime(r.completed_at),
            stored_logic=r.stored_logic,
            proposed_logic=r.proposed_logic,
            status=_queue_status_to_response_status(_record_queue_status(r)),
            queue_status=_record_queue_status(r),
        )
        for r in refreshed_results
    ]

    return BacktestResultsResponse(results=items)
