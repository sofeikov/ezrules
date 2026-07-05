from __future__ import annotations

import datetime
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from ezrules.backend.integrations import publish_integration_event
from ezrules.backend.runtime_settings import get_neutral_outcome
from ezrules.models.backend_core import AllowedOutcome, Case, CaseEvent, EvaluationDecision
from ezrules.models.database import db_session
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)

CASE_STATUS_OPEN = "open"
CASE_STATUS_IN_REVIEW = "in_review"
CASE_STATUS_REOPENED = "reopened"
CASE_STATUS_RESOLVED = "resolved"
CASE_STATUS_CLOSED = "closed"
ACTIVE_CASE_STATUSES = (CASE_STATUS_OPEN, CASE_STATUS_IN_REVIEW, CASE_STATUS_REOPENED)

CASE_DECISION_CURRENT = "current"
CASE_DECISION_RESCORED_NEUTRAL = "rescored_neutral"
CASE_DECISION_RESCORED_NON_CASEABLE = "rescored_non_caseable"


class CaseConflictError(Exception):
    """Raised when a case action was based on a stale decision pointer."""


class CaseNotFoundError(Exception):
    """Raised when a case does not exist in the caller's organisation."""


@dataclass(frozen=True, slots=True)
class CaseProcessingResult:
    case_id: int | None
    action: str


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _new_case_event_id() -> str:
    return f"case_evt_{uuid.uuid4().hex}"


def _event_type_for_integration(case_event_type: str) -> str:
    return f"case.{case_event_type}"


def _outcome_priority(db: Any, *, o_id: int, outcome: str | None) -> int:
    if not outcome:
        return 0
    row = (
        db.query(AllowedOutcome.severity_rank)
        .filter(AllowedOutcome.o_id == o_id, AllowedOutcome.outcome_name == outcome)
        .first()
    )
    return int(row[0]) if row is not None else 0


def _is_caseable_outcome(db: Any, *, o_id: int, outcome: str | None) -> bool:
    if not outcome:
        return False
    return outcome != get_neutral_outcome(db, o_id)


def _active_case_for_transaction(db: Any, *, o_id: int, transaction_id: str) -> Case | None:
    return (
        db.query(Case)
        .filter(
            Case.o_id == o_id,
            Case.transaction_id == transaction_id,
            Case.status.in_(ACTIVE_CASE_STATUSES),
        )
        .order_by(Case.case_id.desc())
        .with_for_update()
        .first()
    )


def _latest_inactive_case_for_transaction(db: Any, *, o_id: int, transaction_id: str) -> Case | None:
    return (
        db.query(Case)
        .filter(
            Case.o_id == o_id,
            Case.transaction_id == transaction_id,
            Case.status.in_([CASE_STATUS_RESOLVED, CASE_STATUS_CLOSED]),
        )
        .order_by(Case.updated_at.desc(), Case.case_id.desc())
        .first()
    )


def _case_payload(case: Case) -> dict[str, Any]:
    return {
        "case_id": int(case.case_id),
        "transaction_id": str(case.transaction_id),
        "status": str(case.status),
        "decision_state": str(case.decision_state),
        "resolved_outcome": str(case.resolved_outcome) if case.resolved_outcome else None,
        "previous_resolved_outcome": str(case.previous_resolved_outcome) if case.previous_resolved_outcome else None,
        "current_evaluation_decision_id": int(case.current_ed_id),
        "previous_evaluation_decision_id": int(case.previous_ed_id) if case.previous_ed_id is not None else None,
        "opened_by_evaluation_decision_id": int(case.opened_by_ed_id),
    }


def record_case_event(
    db: Any,
    *,
    case: Case,
    event_type: str,
    actor_user_id: int | None = None,
    source_ed_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> CaseEvent:
    now = _utcnow()
    case_event = CaseEvent(
        case_id=int(case.case_id),
        o_id=int(case.o_id),
        event_type=event_type,
        actor_user_id=actor_user_id,
        source_ed_id=source_ed_id,
        external_event_id=_new_case_event_id(),
        occurred_at=now,
        details=details or {},
        created_at=now,
    )
    db.add(case_event)
    db.flush()

    publish_integration_event(
        db,
        o_id=int(case.o_id),
        source_type="case_event",
        source_id=int(case_event.case_event_id),
        event_type=_event_type_for_integration(event_type),
        external_event_id=f"evt_case_event_{case_event.case_event_id}",
        occurred_at=now,
        payload={
            "case": _case_payload(case),
            "case_event": {
                "case_event_id": int(case_event.case_event_id),
                "event_type": event_type,
                "external_event_id": str(case_event.external_event_id),
                "details": case_event.details,
            },
            "actor": {"user_id": actor_user_id},
        },
    )
    return case_event


def publish_evaluation_completed(
    db: Any,
    *,
    o_id: int,
    evaluation_decision_id: int,
    case_id: int | None = None,
) -> None:
    decision = (
        db.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == o_id, EvaluationDecision.ed_id == evaluation_decision_id)
        .first()
    )
    if decision is None:
        return
    publish_integration_event(
        db,
        o_id=o_id,
        source_type="evaluation_decision",
        source_id=evaluation_decision_id,
        event_type="evaluation.completed",
        external_event_id=f"evt_evaluation_completed_{evaluation_decision_id}",
        occurred_at=decision.evaluated_at,
        payload={
            "evaluation_decision_id": evaluation_decision_id,
            "transaction_id": str(decision.transaction_id),
            "event_version": int(decision.event_version),
            "resolved_outcome": str(decision.resolved_outcome) if decision.resolved_outcome else None,
            "outcome_counters": decision.outcome_counters if isinstance(decision.outcome_counters, dict) else {},
            "decision_type": str(decision.decision_type),
            "served": bool(decision.served),
            "is_current": bool(decision.is_current),
            "case_id": case_id,
        },
    )


def ensure_case_for_decision(db: Any, *, o_id: int, evaluation_decision_id: int) -> CaseProcessingResult:
    decision = (
        db.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == o_id, EvaluationDecision.ed_id == evaluation_decision_id)
        .first()
    )
    if decision is None:
        return CaseProcessingResult(case_id=None, action="missing_decision")

    if not bool(decision.served) or decision.decision_type != "served" or not bool(decision.is_current):
        return CaseProcessingResult(case_id=None, action="ignored_decision")

    outcome = str(decision.resolved_outcome) if decision.resolved_outcome else None
    caseable = _is_caseable_outcome(db, o_id=o_id, outcome=outcome)
    active_case = _active_case_for_transaction(db, o_id=o_id, transaction_id=str(decision.transaction_id))

    if active_case is not None:
        if int(active_case.current_ed_id) == evaluation_decision_id:
            return CaseProcessingResult(case_id=int(active_case.case_id), action="unchanged")

        previous_ed_id = int(active_case.current_ed_id)
        previous_outcome = str(active_case.resolved_outcome) if active_case.resolved_outcome else None
        active_case.previous_ed_id = previous_ed_id
        active_case.previous_resolved_outcome = previous_outcome
        active_case.current_ed_id = evaluation_decision_id
        active_case.current_ev_id = int(decision.ev_id)
        active_case.resolved_outcome = outcome
        active_case.priority = _outcome_priority(db, o_id=o_id, outcome=outcome)
        if caseable:
            active_case.decision_state = CASE_DECISION_CURRENT
            event_type = "rescored"
        else:
            active_case.decision_state = (
                CASE_DECISION_RESCORED_NEUTRAL if outcome else CASE_DECISION_RESCORED_NON_CASEABLE
            )
            event_type = "rescored_non_caseable"
        active_case.updated_at = _utcnow()
        db.flush()
        record_case_event(
            db,
            case=active_case,
            event_type=event_type,
            source_ed_id=evaluation_decision_id,
            details={
                "previous_evaluation_decision_id": previous_ed_id,
                "current_evaluation_decision_id": evaluation_decision_id,
                "previous_resolved_outcome": previous_outcome,
                "current_resolved_outcome": outcome,
            },
        )
        return CaseProcessingResult(case_id=int(active_case.case_id), action=event_type)

    if not caseable:
        return CaseProcessingResult(case_id=None, action="not_caseable")

    prior_case = _latest_inactive_case_for_transaction(db, o_id=o_id, transaction_id=str(decision.transaction_id))
    case = Case(
        o_id=o_id,
        transaction_id=str(decision.transaction_id),
        current_ev_id=int(decision.ev_id),
        current_ed_id=evaluation_decision_id,
        opened_by_ed_id=evaluation_decision_id,
        resolved_outcome=outcome,
        status=CASE_STATUS_OPEN,
        decision_state=CASE_DECISION_CURRENT,
        priority=_outcome_priority(db, o_id=o_id, outcome=outcome),
        reopened_from_case_id=int(prior_case.case_id) if prior_case is not None else None,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(case)
    db.flush()
    record_case_event(
        db,
        case=case,
        event_type="created",
        source_ed_id=evaluation_decision_id,
        details={
            "current_evaluation_decision_id": evaluation_decision_id,
            "resolved_outcome": outcome,
            "reopened_from_case_id": int(prior_case.case_id) if prior_case is not None else None,
        },
    )
    return CaseProcessingResult(case_id=int(case.case_id), action="created")


def process_evaluation_for_cases(db: Any, *, o_id: int, evaluation_decision_id: int) -> CaseProcessingResult:
    result = ensure_case_for_decision(db, o_id=o_id, evaluation_decision_id=evaluation_decision_id)
    publish_evaluation_completed(db, o_id=o_id, evaluation_decision_id=evaluation_decision_id, case_id=result.case_id)
    return result


def enqueue_case_detection(*, o_id: int, evaluation_decision_id: int, resolved_outcome: str | None = None) -> None:
    if app_settings.TESTING:
        process_evaluation_for_cases(db_session, o_id=o_id, evaluation_decision_id=evaluation_decision_id)
        db_session.commit()
        return

    try:
        from ezrules.backend.tasks import process_evaluation_for_cases_task

        process_evaluation_for_cases_task.delay(o_id, evaluation_decision_id)
    except Exception:
        logger.exception(
            "Failed to enqueue case detection for org_id=%s evaluation_decision_id=%s",
            o_id,
            evaluation_decision_id,
        )


def get_case_for_update(db: Any, *, o_id: int, case_id: int) -> Case:
    case = db.query(Case).filter(Case.o_id == o_id, Case.case_id == case_id).with_for_update().first()
    if case is None:
        raise CaseNotFoundError(f"Case {case_id} not found")
    return case


def assign_case(db: Any, *, o_id: int, case_id: int, actor_user_id: int, assignee_user_id: int | None) -> Case:
    case = get_case_for_update(db, o_id=o_id, case_id=case_id)
    previous_assignee = int(case.assigned_to_user_id) if case.assigned_to_user_id is not None else None
    case.assigned_to_user_id = assignee_user_id
    if case.status == CASE_STATUS_OPEN:
        case.status = CASE_STATUS_IN_REVIEW
    case.updated_at = _utcnow()
    db.flush()
    record_case_event(
        db,
        case=case,
        event_type="assigned",
        actor_user_id=actor_user_id,
        source_ed_id=int(case.current_ed_id),
        details={
            "previous_assigned_to_user_id": previous_assignee,
            "assigned_to_user_id": assignee_user_id,
        },
    )
    return case


def resolve_case(
    db: Any,
    *,
    o_id: int,
    case_id: int,
    actor_user_id: int,
    resolution_note: str,
    resolution_label_id: int | None = None,
    expected_current_ed_id: int | None = None,
) -> Case:
    case = get_case_for_update(db, o_id=o_id, case_id=case_id)
    if expected_current_ed_id is not None and int(case.current_ed_id) != expected_current_ed_id:
        raise CaseConflictError("Case score changed; reload before resolving")

    previous_status = str(case.status)
    case.status = CASE_STATUS_RESOLVED
    case.resolved_by_user_id = actor_user_id
    case.resolution_note = resolution_note.strip()
    case.resolution_label_id = resolution_label_id
    case.resolved_at = _utcnow()
    case.assigned_to_user_id = None
    case.updated_at = _utcnow()
    db.flush()
    record_case_event(
        db,
        case=case,
        event_type="resolved",
        actor_user_id=actor_user_id,
        source_ed_id=int(case.current_ed_id),
        details={
            "previous_status": previous_status,
            "status": CASE_STATUS_RESOLVED,
            "resolution_note": case.resolution_note,
            "resolution_label_id": resolution_label_id,
        },
    )
    return case
