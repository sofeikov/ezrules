"""
FastAPI routes for event evaluation.

These endpoints provide the rule evaluation engine, merged into the
main API service. No authentication required — designed for
service-to-service / internal use.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import get_db
from ezrules.backend.api_v2.schemas.evaluator import EvaluateRequest, EvaluateResponse
from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.type_casting import CastError, cast_event
from ezrules.models.backend_core import ShadowResultsLog
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2", tags=["Evaluator"])

# Lazily-initialised rule executor — created on first request so that
# module import doesn't hit the database during test collection.
_lre: LocalRuleExecutorSQL | None = None
_shadow_lre: LocalRuleExecutorSQL | None = None


def _get_rule_executor(db=Depends(get_db)) -> LocalRuleExecutorSQL:  # noqa: B008
    """Return the shared LocalRuleExecutorSQL instance, creating it on first call."""
    global _lre  # noqa: PLW0603
    if _lre is None:
        _lre = LocalRuleExecutorSQL(db=db, o_id=app_settings.ORG_ID)
    return _lre


def _get_shadow_executor(db=Depends(get_db)) -> LocalRuleExecutorSQL:  # noqa: B008
    """Return the shared shadow LocalRuleExecutorSQL instance, creating it on first call."""
    global _shadow_lre  # noqa: PLW0603
    if _shadow_lre is None:
        _shadow_lre = LocalRuleExecutorSQL(db=db, o_id=app_settings.ORG_ID, label="shadow")
    return _shadow_lre


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request_data: EvaluateRequest,
    lre: LocalRuleExecutorSQL = Depends(_get_rule_executor),
    shadow_lre: LocalRuleExecutorSQL = Depends(_get_shadow_executor),
    db: Any = Depends(get_db),
) -> EvaluateResponse:
    """
    Evaluate an event against the current rule engine configuration.

    Stores the event and its evaluation results in the database.
    Records field observations for type management.
    Also performs a best-effort shadow evaluation if a shadow config exists.
    """
    configs = load_cast_configs(db, lre.o_id)
    try:
        event_data = cast_event(request_data.event_data, configs)
    except CastError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    event = Event(
        event_id=request_data.event_id,
        event_timestamp=request_data.event_timestamp,
        event_data=event_data,
    )
    try:
        result, tl_id = eval_and_store(lre, event)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {exc}",
        ) from exc

    # Best-effort shadow evaluation — never fails the main request
    try:
        shadow_result = shadow_lre.evaluate_rules(event.event_data)
        for r_id, rule_result in shadow_result.get("all_rule_results", {}).items():
            shadow_log = ShadowResultsLog(tl_id=tl_id, r_id=int(r_id), rule_result=str(rule_result))
            db.add(shadow_log)
        db.commit()
    except Exception:
        pass

    record_observations(db, request_data.event_data, lre.o_id)

    return EvaluateResponse(
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
    )
