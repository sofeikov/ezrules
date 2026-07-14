"""
FastAPI routes for event evaluation.

These endpoints provide the rule evaluation engine, merged into the
main API service. Requests must authenticate with either an API key
or a Bearer token.
"""

import hashlib
import logging
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend import data_utils
from ezrules.backend.alerts import enqueue_alert_detection
from ezrules.backend.api_v2.auth.dependencies import get_current_evaluator_org_id, get_db, require_permission
from ezrules.backend.api_v2.schemas.evaluator import (
    EvaluateRequest,
    EvaluateResponse,
    EventTestResponse,
    EventTestRuleResult,
)
from ezrules.backend.cases import enqueue_case_detection
from ezrules.backend.data_utils import Event
from ezrules.backend.features import FeatureResolutionError, FeatureResolutionTrace, FeatureResolver
from ezrules.backend.observation_queue import enqueue_observations
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.runtime_settings import get_main_rule_execution_mode
from ezrules.backend.shadow_evaluation_queue import (
    enqueue_shadow_evaluation,
    load_shadow_evaluation_snapshot,
)
from ezrules.backend.utils import load_cast_configs, record_observations
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import MissingFieldLookupError, MissingStatLookupError, RuleFactory
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
from ezrules.models.backend_core import Rule as RuleModel
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
    return str(event.transaction_id)


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


def _resolve_dry_run_response(db: Any, o_id: int, result: dict[str, Any]) -> dict[str, Any]:
    result["outcome_set"] = sorted(result.get("outcome_set") or [])
    result["resolved_outcome"] = DatabaseOutcome(db_session=db, o_id=o_id).resolve_outcome(result["outcome_counters"])
    result["transaction_id"] = ""
    result["event_version"] = None
    result["event_version_id"] = None
    result["evaluation_id"] = None
    result["evaluation_status"] = "new"
    result["is_current"] = None
    result["superseded_evaluation_id"] = None
    return result


def _serialize_rule_result(value: Any) -> str | None:
    return str(value) if value is not None else None


def _build_event_test_rule_results(db: Any, o_id: int, all_rule_results: dict[Any, Any]) -> list[EventTestRuleResult]:
    rule_ids = [int(rule_id) for rule_id in all_rule_results if str(rule_id).isdigit()]
    rules_by_id = {
        int(rule.r_id): rule
        for rule in db.query(RuleModel).filter(RuleModel.o_id == o_id, RuleModel.r_id.in_(rule_ids)).all()
    }

    results: list[EventTestRuleResult] = []
    for rule_id, outcome in all_rule_results.items():
        if not str(rule_id).isdigit():
            continue
        numeric_rule_id = int(rule_id)
        rule = rules_by_id.get(numeric_rule_id)
        if rule is None:
            continue
        serialized_outcome = _serialize_rule_result(outcome)
        results.append(
            EventTestRuleResult(
                r_id=numeric_rule_id,
                rid=str(rule.rid),
                description=str(rule.description),
                evaluation_lane=str(rule.evaluation_lane),
                outcome=serialized_outcome,
                matched=serialized_outcome is not None,
            )
        )
    return results


def _get_deployment_stat_paths(
    deployment_entries: list[dict[str, Any]],
    list_provider: PersistentUserListManager,
    deployment_label: str,
) -> set[str]:
    stat_paths: set[str] = set()
    for entry in deployment_entries:
        try:
            stat_paths.update(RuleFactory.from_json(entry, list_values_provider=list_provider).get_rule_stats())
        except Exception:
            logger.debug("Skipping stat pre-resolution for invalid %s candidate", deployment_label, exc_info=True)
    return stat_paths


def _resolve_evaluation_stats(
    *,
    db: Any,
    o_id: int,
    event_data: dict[str, Any],
    as_of: datetime,
    lre: LocalRuleExecutorSQL,
    rollout_entries: list[dict[str, Any]],
    shadow_entries: list[dict[str, Any]],
    list_provider: PersistentUserListManager | None,
) -> tuple[dict[str, Any], list[FeatureResolutionTrace]]:
    stat_paths = lre.get_rule_stats()
    if rollout_entries and list_provider is not None:
        stat_paths.update(_get_deployment_stat_paths(rollout_entries, list_provider, ROLLOUT_CONFIG_LABEL))
    if shadow_entries and list_provider is not None:
        stat_paths.update(_get_deployment_stat_paths(shadow_entries, list_provider, "shadow"))
    return FeatureResolver(db, o_id).resolve_with_traces(event_data, as_of, stat_paths)


def _evaluate_rollout_result(
    *,
    event_data: dict[str, Any],
    lre: LocalRuleExecutorSQL,
    rollout_entries: list[dict[str, Any]],
    assignment_key: str,
    list_provider: PersistentUserListManager,
    stats: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[int, dict[str, Any]]]:
    ordered_rules = list(lre.rule_engine.rules if lre.rule_engine is not None else [])
    rollout_by_rule_id = {int(entry["r_id"]): entry for entry in rollout_entries if "r_id" in entry}
    rule_metadata_by_id = data_utils.build_rule_metadata_from_rules(ordered_rules)
    all_rule_results: dict[int, Any] = {}
    rollout_logs: list[dict[str, Any]] = []

    for control_rule in ordered_rules:
        rule_id = int(control_rule.r_id)
        control_result = control_rule(event_data, stats=stats)
        returned_result = control_result

        entry = rollout_by_rule_id.get(rule_id)
        if entry is not None:
            traffic_percent = int(entry.get("traffic_percent") or 0)
            bucket = _get_rollout_bucket(lre.o_id, rule_id, assignment_key)
            candidate_result = None
            candidate_succeeded = False
            try:
                candidate_rule = RuleFactory.from_json(entry, list_values_provider=list_provider)
                candidate_result = candidate_rule(event_data, stats=stats)
                candidate_succeeded = True
            except Exception:
                candidate_result = None

            selected_variant = DEPLOYMENT_VARIANT_CANDIDATE if bucket < traffic_percent else DEPLOYMENT_VARIANT_CONTROL
            if selected_variant == DEPLOYMENT_VARIANT_CANDIDATE and candidate_succeeded:
                returned_result = candidate_result
                rule_metadata_by_id.update(data_utils.build_rule_metadata_from_rules([candidate_rule]))

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

    return _build_response_from_all_results(all_rule_results), rollout_logs, rule_metadata_by_id


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
        transaction_id=request_data.transaction_id,
        effective_at=request_data.effective_at,
        observed_at=request_data.observed_at,
        terminal_state=request_data.terminal_state,
        event_data=event_data,
    )
    data_utils.lock_transaction_for_evaluation(db, lre.o_id, event.transaction_id)
    duplicate = data_utils.find_duplicate_evaluation(db, lre.o_id, event)
    if duplicate is not None:
        duplicate_evaluation_id = duplicate.get("evaluation_id")
        if duplicate_evaluation_id is not None:
            enqueue_alert_detection(
                o_id=int(lre.o_id),
                evaluation_decision_id=int(duplicate_evaluation_id),
                resolved_outcome=duplicate.get("resolved_outcome"),
            )
            enqueue_case_detection(
                o_id=int(lre.o_id),
                evaluation_decision_id=int(duplicate_evaluation_id),
            )
        return EvaluateResponse(
            transaction_id=duplicate["transaction_id"],
            outcome_counters=duplicate["outcome_counters"],
            outcome_set=duplicate["outcome_set"],
            resolved_outcome=duplicate.get("resolved_outcome"),
            rule_results={str(k): str(v) for k, v in duplicate["rule_results"].items()},
            event_version=duplicate.get("event_version"),
            event_version_id=duplicate.get("event_version_id"),
            evaluation_id=duplicate.get("evaluation_id"),
            evaluation_status=duplicate.get("evaluation_status", "duplicate"),
            is_current=duplicate.get("is_current"),
            superseded_evaluation_id=duplicate.get("superseded_evaluation_id"),
        )
    try:
        allowlist_result = allowlist_lre.evaluate_rules(event.event_data, as_of=event.effective_at)
        if allowlist_result.get("rule_results"):
            result = _build_response_from_all_results(dict(allowlist_result.get("all_rule_results", {})))
            result["_rule_metadata_by_id"] = data_utils.build_rule_metadata_from_engine(allowlist_lre.rule_engine)
            result, _ = data_utils.eval_and_store(lre, event, response=result)
            enqueue_alert_detection(
                o_id=int(lre.o_id),
                evaluation_decision_id=int(result["evaluation_decision_id"]),
                resolved_outcome=result.get("resolved_outcome"),
            )
            enqueue_case_detection(
                o_id=int(lre.o_id),
                evaluation_decision_id=int(result["evaluation_decision_id"]),
            )
            _persist_evaluate_observations(db, request_data.event_data, lre.o_id)
            return EvaluateResponse(
                transaction_id=result["transaction_id"],
                outcome_counters=result["outcome_counters"],
                outcome_set=result["outcome_set"],
                resolved_outcome=result.get("resolved_outcome"),
                rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
                event_version=result.get("event_version"),
                event_version_id=result.get("event_version_id"),
                evaluation_id=result.get("evaluation_id"),
                evaluation_status=result.get("evaluation_status", "new"),
                is_current=result.get("is_current"),
                superseded_evaluation_id=result.get("superseded_evaluation_id"),
            )

        shadow_snapshot = load_shadow_evaluation_snapshot(db, lre.o_id)
        shadow_entries = list(shadow_snapshot.config) if shadow_snapshot is not None else []
        rollout_entries = list_candidate_deployments(db, lre.o_id, ROLLOUT_CONFIG_LABEL)
        list_provider = PersistentUserListManager(db, lre.o_id) if rollout_entries or shadow_entries else None
        stats, feature_traces = _resolve_evaluation_stats(
            db=db,
            o_id=lre.o_id,
            event_data=event.event_data,
            as_of=event.effective_at,
            lre=lre,
            rollout_entries=rollout_entries,
            shadow_entries=shadow_entries,
            list_provider=list_provider,
        )
        production_result = lre.evaluate_rules(event.event_data, as_of=event.effective_at, stats=stats)
    except (FeatureResolutionError, MissingFieldLookupError, MissingStatLookupError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed",
        ) from exc

    rollout_logs: list[dict[str, Any]] = []
    if rollout_entries:
        assert list_provider is not None
        assignment_key = _get_assignment_key(event)
        result, rollout_logs, rule_metadata_by_id = _evaluate_rollout_result(
            event_data=event.event_data,
            lre=lre,
            rollout_entries=rollout_entries,
            assignment_key=assignment_key,
            list_provider=list_provider,
            stats=stats,
        )
        result["_rule_metadata_by_id"] = rule_metadata_by_id
    else:
        result = production_result

    try:
        # `result` already contains the merged served outcome; passing it avoids a second rule evaluation.
        result, evaluation_decision_id = data_utils.eval_and_store(lre, event, response=result)
        enqueue_alert_detection(
            o_id=int(lre.o_id),
            evaluation_decision_id=int(evaluation_decision_id),
            resolved_outcome=result.get("resolved_outcome"),
        )
        enqueue_case_detection(
            o_id=int(lre.o_id),
            evaluation_decision_id=int(evaluation_decision_id),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed",
        ) from exc

    try:
        FeatureResolver(db, lre.o_id).persist_traces(feature_traces, evaluation_decision_id=int(evaluation_decision_id))
        db.commit()
    except Exception:
        logger.exception(
            "Failed to persist feature traces for evaluation_decision_id=%s org_id=%s",
            evaluation_decision_id,
            lre.o_id,
        )
        db.rollback()

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
                event.transaction_id,
                lre.o_id,
            )
            try:
                db.rollback()
            except Exception:
                logger.exception(
                    "Failed to rollback rollout comparison log transaction for event_id=%s org_id=%s",
                    event.transaction_id,
                    lre.o_id,
                )

    if shadow_snapshot is not None:
        enqueue_shadow_evaluation(
            db=db,
            o_id=int(lre.o_id),
            event_id=str(event.transaction_id),
            event_data=event.event_data,
            stats=stats,
            production_all_rule_results=dict(production_result.get("all_rule_results", {})),
            evaluation_decision_id=int(result["evaluation_id"]),
            event_version_id=int(result["event_version_id"]),
            shadow_snapshot=shadow_snapshot,
        )

    _persist_evaluate_observations(db, request_data.event_data, lre.o_id)

    return EvaluateResponse(
        transaction_id=result["transaction_id"],
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        resolved_outcome=result.get("resolved_outcome"),
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
        event_version=result.get("event_version"),
        event_version_id=result.get("event_version_id"),
        evaluation_id=result.get("evaluation_id"),
        evaluation_status=result.get("evaluation_status", "new"),
        is_current=result.get("is_current"),
        superseded_evaluation_id=result.get("superseded_evaluation_id"),
    )


@router.post("/event-tests", response_model=EventTestResponse)
def test_event(
    request_data: EvaluateRequest,
    lre: LocalRuleExecutorSQL = Depends(_get_rule_executor),
    allowlist_lre: LocalRuleExecutorSQL = Depends(_get_allowlist_executor),
    db: Any = Depends(get_db),
    _: None = Depends(require_permission(PermissionAction.SUBMIT_TEST_EVENTS)),
) -> EventTestResponse:
    """
    Dry-run an event against the current rule engine configuration.

    This mirrors live evaluation behavior but does not store the event, write
    rollout/shadow logs, enqueue shadow work, or record field observations.
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
        transaction_id=request_data.transaction_id,
        effective_at=request_data.effective_at,
        observed_at=request_data.observed_at,
        terminal_state=request_data.terminal_state,
        event_data=event_data,
    )

    skipped_main_rules = False
    result: dict[str, Any]
    try:
        allowlist_result = allowlist_lre.evaluate_rules(event.event_data, as_of=event.effective_at)
        if allowlist_result.get("rule_results"):
            result = _build_response_from_all_results(dict(allowlist_result.get("all_rule_results", {})))
            skipped_main_rules = True
        else:
            rollout_entries = list_candidate_deployments(db, lre.o_id, ROLLOUT_CONFIG_LABEL)
            list_provider = PersistentUserListManager(db, lre.o_id) if rollout_entries else None
            stats, _feature_traces = _resolve_evaluation_stats(
                db=db,
                o_id=lre.o_id,
                event_data=event.event_data,
                as_of=event.effective_at,
                lre=lre,
                rollout_entries=rollout_entries,
                shadow_entries=[],
                list_provider=list_provider,
            )
            production_result = lre.evaluate_rules(event.event_data, as_of=event.effective_at, stats=stats)
            if rollout_entries:
                assert list_provider is not None
                result, rollout_logs, _rule_metadata_by_id = _evaluate_rollout_result(
                    event_data=event.event_data,
                    lre=lre,
                    rollout_entries=rollout_entries,
                    assignment_key=_get_assignment_key(event),
                    list_provider=list_provider,
                    stats=stats,
                )
                del rollout_logs
            else:
                result = production_result
    except (FeatureResolutionError, MissingFieldLookupError, MissingStatLookupError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event test failed",
        ) from exc

    result = _resolve_dry_run_response(db, lre.o_id, result)
    all_rule_results = dict(result.get("all_rule_results") or result.get("rule_results") or {})

    return EventTestResponse(
        transaction_id=request_data.transaction_id,
        dry_run=True,
        skipped_main_rules=skipped_main_rules,
        outcome_counters=result["outcome_counters"],
        outcome_set=result["outcome_set"],
        resolved_outcome=result.get("resolved_outcome"),
        rule_results={str(k): str(v) for k, v in result["rule_results"].items()},
        event_version=None,
        event_version_id=None,
        evaluation_id=None,
        evaluation_status="new",
        is_current=None,
        superseded_evaluation_id=None,
        all_rule_results={str(k): _serialize_rule_result(v) for k, v in all_rule_results.items()},
        evaluated_rules=_build_event_test_rule_results(db, lre.o_id, all_rule_results),
    )
