"""
FastAPI routes for event evaluation.

These endpoints provide the rule evaluation engine, merged into the
main API service. No authentication required — designed for
service-to-service / internal use.
"""

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import get_db
from ezrules.backend.api_v2.schemas.evaluator import EvaluateRequest, EvaluateResponse
from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.utils import load_cast_configs
from ezrules.core.type_casting import CastError, cast_event
from ezrules.models.backend_core import FieldObservation
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


def _record_observations(db: Any, event_data: dict, o_id: int) -> None:
    """Upsert a FieldObservation row for every field in the event."""
    now = datetime.datetime.now(datetime.UTC)
    for field_name, value in event_data.items():
        observed_type = type(value).__name__
        existing = (
            db.query(FieldObservation)
            .filter(
                FieldObservation.field_name == field_name,
                FieldObservation.observed_json_type == observed_type,
                FieldObservation.o_id == o_id,
            )
            .first()
        )
        if existing:
            existing.observed_json_type = observed_type
            existing.last_seen = now
            existing.occurrence_count = (existing.occurrence_count or 0) + 1
        else:
            db.add(
                FieldObservation(
                    field_name=field_name,
                    observed_json_type=observed_type,
                    last_seen=now,
                    occurrence_count=1,
                    o_id=o_id,
                )
            )
    db.commit()


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request_data: EvaluateRequest,
    lre: LocalRuleExecutorSQL = Depends(_get_rule_executor),
    db: Any = Depends(get_db),
) -> EvaluateResponse:
    """
    Evaluate an event against the current rule engine configuration.

    Stores the event and its evaluation results in the database.
    Records field observations for type management.
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
        result = eval_and_store(lre, event)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {exc}",
        ) from exc

    _record_observations(db, request_data.event_data, lre.o_id)

    return EvaluateResponse(
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
    )
