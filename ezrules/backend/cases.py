from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from ezrules.backend.integrations import publish_integration_event
from ezrules.backend.runtime_settings import get_neutral_outcome
from ezrules.models.backend_core import (
    AllowedOutcome,
    Case,
    CaseEvent,
    EvaluationDecision,
    IntegrationEvent,
    Label,
    User,
)
from ezrules.models.database import db_session

CASE_STATUS_OPEN = "open"
CASE_STATUS_IN_REVIEW = "in_review"
CASE_STATUS_REOPENED = "reopened"
CASE_STATUS_RESOLVED = "resolved"
CASE_STATUS_CLOSED = "closed"
ACTIVE_CASE_STATUSES = (CASE_STATUS_OPEN, CASE_STATUS_IN_REVIEW, CASE_STATUS_REOPENED)

CASE_DECISION_CURRENT = "current"
CASE_DECISION_RESCORED_NEUTRAL = "rescored_neutral"
CASE_DECISION_RESCORED_NON_CASEABLE = "rescored_non_caseable"
CASE_RESOLUTION_DISPOSITIONS = frozenset(
    {
        "confirmed_fraud",
        "false_positive",
        "approved",
        "rejected",
        "duplicate",
        "unable_to_verify",
        "escalated",
    }
)
CASE_RESOLUTION_ACTIONS = frozenset(
    {
        "none",
        "release_transaction",
        "cancel_transaction",
        "block_customer",
        "escalate_external_review",
    }
)


class CaseConflictError(Exception):
    """Raised when a case action was based on a stale decision pointer."""


class CaseNotFoundError(Exception):
    """Raised when a case does not exist in the caller's organisation."""


class CaseValidationError(Exception):
    """Raised when a case mutation payload is invalid for the caller's organisation."""


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
    return outcome.upper() != get_neutral_outcome(db, o_id).upper()


def _lock_case_transaction(db: Any, *, o_id: int, transaction_id: str) -> None:
    db.execute(
        sa.text("SELECT pg_advisory_xact_lock(:o_id, hashtext(:transaction_id))"),
        {"o_id": o_id, "transaction_id": transaction_id},
    )


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
        "current_event_version_id": int(case.current_ev_id),
        "current_evaluation_decision_id": int(case.current_ed_id),
        "previous_evaluation_decision_id": int(case.previous_ed_id) if case.previous_ed_id is not None else None,
        "opened_by_evaluation_decision_id": int(case.opened_by_ed_id),
        "status": str(case.status),
        "decision_state": str(case.decision_state),
        "priority": int(case.priority),
        "resolved_outcome": str(case.resolved_outcome) if case.resolved_outcome else None,
        "previous_resolved_outcome": str(case.previous_resolved_outcome) if case.previous_resolved_outcome else None,
        "assigned_to_user_id": int(case.assigned_to_user_id) if case.assigned_to_user_id is not None else None,
        "resolved_by_user_id": int(case.resolved_by_user_id) if case.resolved_by_user_id is not None else None,
        "resolution_disposition": str(case.resolution_disposition) if case.resolution_disposition else None,
        "resolution_action": str(case.resolution_action) if case.resolution_action else None,
        "resolution_note": str(case.resolution_note) if case.resolution_note else None,
        "resolution_label_id": int(case.resolution_label_id) if case.resolution_label_id is not None else None,
        "reopened_from_case_id": int(case.reopened_from_case_id) if case.reopened_from_case_id is not None else None,
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


def _downstream_action_payload(case: Case, *, event_type: str) -> dict[str, Any]:
    action = str(case.resolution_action) if case.resolution_action else "none"
    requested = event_type == "resolved" and action != "none"
    return {
        "requested": requested,
        "action": action,
        "status": "requested" if requested else "none",
        "source": "analyst_resolution" if event_type == "resolved" else "case_lifecycle_event",
        "executed_by_ezrules": False,
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

    case_payload = _case_payload(case)
    publish_integration_event(
        db,
        o_id=int(case.o_id),
        source_type="case_event",
        source_id=int(case_event.case_event_id),
        event_type=_event_type_for_integration(event_type),
        external_event_id=f"evt_case_event_{case_event.case_event_id}",
        occurred_at=now,
        payload={
            "case_id": case_payload["case_id"],
            "transaction_id": case_payload["transaction_id"],
            "case_event_id": int(case_event.case_event_id),
            "case_event_type": event_type,
            "case_event_external_event_id": str(case_event.external_event_id),
            "actor_user_id": actor_user_id,
            "source_evaluation_decision_id": source_ed_id,
            "current_event_version_id": case_payload["current_event_version_id"],
            "current_evaluation_decision_id": case_payload["current_evaluation_decision_id"],
            "opened_by_evaluation_decision_id": case_payload["opened_by_evaluation_decision_id"],
            "previous_evaluation_decision_id": case_payload["previous_evaluation_decision_id"],
            "status": case_payload["status"],
            "decision_state": case_payload["decision_state"],
            "resolved_outcome": case_payload["resolved_outcome"],
            "previous_resolved_outcome": case_payload["previous_resolved_outcome"],
            "assigned_to_user_id": case_payload["assigned_to_user_id"],
            "resolved_by_user_id": case_payload["resolved_by_user_id"],
            "resolution_disposition": case_payload["resolution_disposition"],
            "resolution_action": case_payload["resolution_action"],
            "resolution_note": case_payload["resolution_note"],
            "resolution_label_id": case_payload["resolution_label_id"],
            "downstream_action": _downstream_action_payload(case, event_type=event_type),
            "occurred_at": now.isoformat(),
            "case": case_payload,
            "case_event": {
                "case_event_id": int(case_event.case_event_id),
                "event_type": event_type,
                "external_event_id": str(case_event.external_event_id),
                "occurred_at": now.isoformat(),
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
    effective_case_id = case_id
    if effective_case_id is None:
        existing_event = (
            db.query(IntegrationEvent.payload)
            .filter(IntegrationEvent.external_event_id == f"evt_evaluation_completed_{evaluation_decision_id}")
            .first()
        )
        existing_payload = (
            existing_event[0] if existing_event is not None and isinstance(existing_event[0], dict) else {}
        )
        existing_case_id = existing_payload.get("case_id")
        effective_case_id = int(existing_case_id) if isinstance(existing_case_id, int) else None

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
            "case_id": effective_case_id,
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
    _lock_case_transaction(db, o_id=o_id, transaction_id=str(decision.transaction_id))
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


def enqueue_case_detection(*, o_id: int, evaluation_decision_id: int) -> None:
    process_evaluation_for_cases(db_session, o_id=o_id, evaluation_decision_id=evaluation_decision_id)
    db_session.commit()


def get_case_for_update(db: Any, *, o_id: int, case_id: int) -> Case:
    case = db.query(Case).filter(Case.o_id == o_id, Case.case_id == case_id).with_for_update().first()
    if case is None:
        raise CaseNotFoundError(f"Case {case_id} not found")
    return case


def assign_case(db: Any, *, o_id: int, case_id: int, actor_user_id: int, assignee_user_id: int | None) -> Case:
    case = get_case_for_update(db, o_id=o_id, case_id=case_id)
    if case.status in {CASE_STATUS_RESOLVED, CASE_STATUS_CLOSED}:
        raise CaseValidationError("Resolved cases cannot be assigned")
    if assignee_user_id is not None:
        assignee = (
            db.query(User.id).filter(User.id == assignee_user_id, User.o_id == o_id, User.active.is_(True)).first()
        )
        if assignee is None:
            raise CaseValidationError("Assignee must be an active user in the case organisation")
    previous_assignee = int(case.assigned_to_user_id) if case.assigned_to_user_id is not None else None
    if previous_assignee == assignee_user_id:
        return case
    case.assigned_to_user_id = assignee_user_id
    if assignee_user_id is None and case.status == CASE_STATUS_IN_REVIEW:
        case.status = CASE_STATUS_OPEN
    elif assignee_user_id is not None and case.status == CASE_STATUS_OPEN:
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


def add_case_note(db: Any, *, o_id: int, case_id: int, actor_user_id: int, note: str) -> CaseEvent:
    case = get_case_for_update(db, o_id=o_id, case_id=case_id)
    return record_case_event(
        db,
        case=case,
        event_type="note",
        actor_user_id=actor_user_id,
        source_ed_id=int(case.current_ed_id),
        details={"note": note.strip()},
    )


def resolve_case(
    db: Any,
    *,
    o_id: int,
    case_id: int,
    actor_user_id: int,
    resolution_disposition: str,
    resolution_action: str,
    resolution_note: str,
    resolution_label_id: int | None = None,
    expected_current_ed_id: int | None = None,
) -> Case:
    case = get_case_for_update(db, o_id=o_id, case_id=case_id)
    if expected_current_ed_id is not None and int(case.current_ed_id) != expected_current_ed_id:
        raise CaseConflictError("Case score changed; reload before resolving")

    if case.status in {CASE_STATUS_RESOLVED, CASE_STATUS_CLOSED}:
        return case

    normalized_disposition = resolution_disposition.strip().lower()
    if normalized_disposition not in CASE_RESOLUTION_DISPOSITIONS:
        raise CaseValidationError("Resolution disposition is not supported")
    normalized_action = resolution_action.strip().lower()
    if normalized_action not in CASE_RESOLUTION_ACTIONS:
        raise CaseValidationError("Resolution action is not supported")

    if resolution_label_id is not None:
        label = db.query(Label.el_id).filter(Label.el_id == resolution_label_id, Label.o_id == o_id).first()
        if label is None:
            raise CaseValidationError("Resolution label must belong to the case organisation")

    previous_status = str(case.status)
    case.status = CASE_STATUS_RESOLVED
    case.resolved_by_user_id = actor_user_id
    case.resolution_disposition = normalized_disposition
    case.resolution_action = normalized_action
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
            "resolution_disposition": normalized_disposition,
            "resolution_action": normalized_action,
            "resolution_note": case.resolution_note,
            "resolution_label_id": resolution_label_id,
        },
    )
    return case
