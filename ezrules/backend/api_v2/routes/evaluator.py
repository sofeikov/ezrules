"""
FastAPI routes for event evaluation.

These endpoints provide the rule evaluation engine, merged into the
main API service. No authentication required — designed for
service-to-service / internal use.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import get_db
from ezrules.backend.api_v2.schemas.evaluator import EvaluateRequest, EvaluateResponse
from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2", tags=["Evaluator"])

# Lazily-initialised rule executor — created on first request so that
# module import doesn't hit the database during test collection.
_lre: LocalRuleExecutorSQL | None = None


def _get_rule_executor(db=Depends(get_db)) -> LocalRuleExecutorSQL:  # noqa: B008
    """Return the shared LocalRuleExecutorSQL instance, creating it on first call."""
    global _lre  # noqa: PLW0603
    if _lre is None:
        _lre = LocalRuleExecutorSQL(db=db, o_id=app_settings.ORG_ID)
    return _lre


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request_data: EvaluateRequest,
    lre: LocalRuleExecutorSQL = Depends(_get_rule_executor),
) -> EvaluateResponse:
    """
    Evaluate an event against the current rule engine configuration.

    Stores the event and its evaluation results in the database.
    """
    event = Event(
        event_id=request_data.event_id,
        event_timestamp=request_data.event_timestamp,
        event_data=request_data.event_data,
    )
    try:
        result = eval_and_store(lre, event)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {exc}",
        ) from exc

    return EvaluateResponse(
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
    )
