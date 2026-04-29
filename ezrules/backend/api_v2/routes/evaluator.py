"""
FastAPI routes for event evaluation.

These endpoints provide the rule evaluation engine, merged into the
main API service. Requests must authenticate with either an API key
or a Bearer token.
"""

import hashlib
import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend import data_utils
from ezrules.backend.api_v2.auth.dependencies import get_current_evaluator_org_id, get_db
from ezrules.backend.api_v2.schemas.evaluator import EvaluateRequest, EvaluateResponse
from ezrules.backend.data_utils import Event
from ezrules.backend.observation_queue import enqueue_observations
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.runtime_settings import get_main_rule_execution_mode
from ezrules.backend.shadow_evaluation_queue import enqueue_shadow_evaluation
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.rule import MissingFieldLookupError, RuleFactory
from ezrules.core.rule_engine import RULE_EXECUTION_MODE_FIRST_MATCH
from ezrules.core.rule_updater import (
    ALLOWLIST_CONFIG_LABEL,
    DEPLOYMENT_MODE_SPLIT,
    DEPLOYMENT_VARIANT_CANDIDATE,
    DEPLOYMENT_VARIANT_CONTROL,
    ROLLOUT_CONFIG_LABEL,
    list_candidate_deployments,
)
from ezrules.core.type_casting import CastError, RequiredFieldError, normalize_event
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import RuleDeploymentResultsLog
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2", tags=["Evaluator"])
logger = logging.getLogger(__name__)

_lre: LocalRuleExecutorSQL | None = None
_shadow_lre: LocalRuleExecutorSQL | None = None
_allowlist_lre: LocalRuleExecutorSQL | None = None


def _get_rule_executor(
    current_org_id: int = Depends(get_current_evaluator_org_id),
    db=Depends(get_db),  # noqa: B008
) -> LocalRuleExecutorSQL:
    """Return the test-injected executor or a request-scoped production executor."""
    if app_settings.TESTING and _lre is not None:
        return _lre
    return LocalRuleExecutorSQL(
        db=db,
        o_id=current_org_id,
        execution_mode=get_main_rule_execution_mode(db, current_org_id),
    )


def _get_shadow_executor(
    current_org_id: int = Depends(get_current_evaluator_org_id),
    db=Depends(get_db),  # noqa: B008
) -> LocalRuleExecutorSQL:
    """Return the test-injected shadow executor or a request-scoped production executor."""
    if app_settings.TESTING and _shadow_lre is not None:
        return _shadow_lre
    return LocalRuleExecutorSQL(
        db=db,
        o_id=current_org_id,
        label="shadow",
        execution_mode=get_main_rule_execution_mode(db, current_org_id),
    )


def _get_allowlist_executor(
    current_org_id: int = Depends(get_current_evaluator_org_id),
    db=Depends(get_db),  # noqa: B008
) -> LocalRuleExecutorSQL:
    """Return the test-injected allowlist executor or a request-scoped executor."""
    if app_settings.TESTING and _allowlist_lre is not None:
        return _allowlist_lre
    return LocalRuleExecutorSQL(db=db, o_id=current_org_id, label=ALLOWLIST_CONFIG_LABEL)


def _get_assignment_key(event: Event) -> str:
    return str(event.event_id)


def _get_rollout_bucket(o_id: int, r_id: int, assignment_key: str) -> int:
    digest = hashlib.sha256(f"{o_id}:{r_id}:{assignment_key}".encode()).hexdigest()
    return int(digest, 16) % 100


def _build_response_from_all_results(all_rule_results: dict[Any, Any]) -> dict[str, Any]:
    rule_results = {r_id: result for r_id, result in all_rule_results.items() if result is not None}
    outcome_counters = dict(Counter(rule_results.values()))
    return {
        "all_rule_results": all_rule_results,
        "rule_results": rule_results,
        "outcome_counters": outcome_counters,
        "outcome_set": sorted(set(outcome_counters.keys())),
    }


def _evaluate_rollout_result(
    *,
    event_data: dict[str, Any],
    lre: LocalRuleExecutorSQL,
    rollout_entries: list[dict[str, Any]],
    assignment_key: str,
    list_provider: PersistentUserListManager,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ordered_rules = list(lre.rule_engine.rules if lre.rule_engine is not None else [])
    rollout_by_rule_id = {int(entry["r_id"]): entry for entry in rollout_entries if "r_id" in entry}
    all_rule_results: dict[int, Any] = {}
    rollout_logs: list[dict[str, Any]] = []

    for control_rule in ordered_rules:
        rule_id = int(control_rule.r_id)
        control_result = control_rule(event_data)
        returned_result = control_result

        entry = rollout_by_rule_id.get(rule_id)
        if entry is not None:
            traffic_percent = int(entry.get("traffic_percent") or 0)
            bucket = _get_rollout_bucket(lre.o_id, rule_id, assignment_key)
            candidate_result = None
            candidate_succeeded = False
            try:
                candidate_rule = RuleFactory.from_json(entry, list_values_provider=list_provider)
                candidate_result = candidate_rule(event_data)
                candidate_succeeded = True
            except Exception:
                candidate_result = None

            selected_variant = DEPLOYMENT_VARIANT_CANDIDATE if bucket < traffic_percent else DEPLOYMENT_VARIANT_CONTROL
            if selected_variant == DEPLOYMENT_VARIANT_CANDIDATE and candidate_succeeded:
                returned_result = candidate_result

            rollout_logs.append(
                {
                    "mode": DEPLOYMENT_MODE_SPLIT,
                    "r_id": rule_id,
                    "selected_variant": selected_variant,
                    "traffic_percent": traffic_percent,
                    "bucket": bucket,
                    "control_result": control_result,
                    "candidate_result": candidate_result,
                    "returned_result": returned_result,
                }
            )

        all_rule_results[rule_id] = returned_result
        if lre.execution_mode == RULE_EXECUTION_MODE_FIRST_MATCH and returned_result is not None:
            break

    return _build_response_from_all_results(all_rule_results), rollout_logs


def _persist_evaluate_observations(db: Any, event_data: dict, o_id: int) -> None:
    if app_settings.TESTING:
        record_observations(db, event_data, o_id)
        return

    enqueue_observations(event_data, o_id)


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request_data: EvaluateRequest,
    lre: LocalRuleExecutorSQL = Depends(_get_rule_executor),
    allowlist_lre: LocalRuleExecutorSQL = Depends(_get_allowlist_executor),
    db: Any = Depends(get_db),
    _: int = Depends(get_current_evaluator_org_id),
) -> EvaluateResponse:
    """
    Evaluate an event against the current rule engine configuration.

    Stores the event and its evaluation results in the database.
    Records field observations for type management.
    Enqueues a best-effort shadow evaluation if a shadow config exists.
    """
    configs = load_cast_configs(db, lre.o_id)
    try:
        event_data = normalize_event(request_data.event_data, configs)
    except (CastError, RequiredFieldError) as exc:
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
        allowlist_result = allowlist_lre.evaluate_rules(event.event_data)
        if allowlist_result.get("rule_results"):
            result = _build_response_from_all_results(dict(allowlist_result.get("all_rule_results", {})))
            result, _ = data_utils.eval_and_store(lre, event, response=result)
            _persist_evaluate_observations(db, request_data.event_data, lre.o_id)
            return EvaluateResponse(
                outcome_counters=result["outcome_counters"],
                outcome_set=result["outcome_set"],
                resolved_outcome=result.get("resolved_outcome"),
                rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
                event_version=result.get("event_version"),
                evaluation_decision_id=result.get("evaluation_decision_id"),
            )

        production_result = lre.evaluate_rules(event.event_data)
    except MissingFieldLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed",
        ) from exc

    rollout_entries = list_candidate_deployments(db, lre.o_id, ROLLOUT_CONFIG_LABEL)
    rollout_logs: list[dict[str, Any]] = []
    if rollout_entries:
        assignment_key = _get_assignment_key(event)
        list_provider = PersistentUserListManager(db, lre.o_id)
        result, rollout_logs = _evaluate_rollout_result(
            event_data=event.event_data,
            lre=lre,
            rollout_entries=rollout_entries,
            assignment_key=assignment_key,
            list_provider=list_provider,
        )
    else:
        result = production_result

    try:
        # `result` already contains the merged served outcome; passing it avoids a second rule evaluation.
        result, evaluation_decision_id = data_utils.eval_and_store(lre, event, response=result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed",
        ) from exc

    if rollout_logs:
        try:
            for log in rollout_logs:
                db.add(
                    RuleDeploymentResultsLog(
                        ed_id=int(evaluation_decision_id),
                        r_id=int(log["r_id"]),
                        o_id=lre.o_id,
                        mode=str(log["mode"]),
                        selected_variant=str(log["selected_variant"]),
                        traffic_percent=int(log["traffic_percent"]) if log["traffic_percent"] is not None else None,
                        bucket=int(log["bucket"]) if log["bucket"] is not None else None,
                        control_result=str(log["control_result"]) if log["control_result"] is not None else None,
                        candidate_result=str(log["candidate_result"]) if log["candidate_result"] is not None else None,
                        returned_result=str(log["returned_result"]) if log["returned_result"] is not None else None,
                    )
                )
            db.commit()
        except Exception:
            logger.exception(
                "Failed to persist rollout comparison logs for event_id=%s org_id=%s",
                event.event_id,
                lre.o_id,
            )
            try:
                db.rollback()
            except Exception:
                logger.exception(
                    "Failed to rollback rollout comparison log transaction for event_id=%s org_id=%s",
                    event.event_id,
                    lre.o_id,
                )

    enqueue_shadow_evaluation(
        db=db,
        o_id=int(lre.o_id),
        event_id=str(event.event_id),
        event_data=event.event_data,
        production_all_rule_results=dict(production_result.get("all_rule_results", {})),
        evaluation_decision_id=int(result["evaluation_decision_id"]),
        event_version_id=int(result["event_version_id"]),
    )

    _persist_evaluate_observations(db, request_data.event_data, lre.o_id)

    return EvaluateResponse(
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        resolved_outcome=result.get("resolved_outcome"),
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
        event_version=result.get("event_version"),
        evaluation_decision_id=result.get("evaluation_decision_id"),
    )
