import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import exists
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from ezrules.backend.cases import ensure_case_for_decision, record_case_event
from ezrules.backend.notifications import NotificationMessage, dispatch_notification
from ezrules.models.backend_core import AlertIncident, AlertIncidentCase, AlertRule, Case, EvaluationDecision
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dedupe_key(rule: AlertRule, window_end: datetime) -> str:
    bucket_seconds = max(int(rule.cooldown_seconds or 0), 60)
    bucket = int(window_end.timestamp()) // bucket_seconds
    return f"rule:{rule.ar_id}:outcome:{rule.outcome}:bucket:{bucket}"


def _incident_in_cooldown(db: Any, rule: AlertRule, now: datetime) -> AlertIncident | None:
    cooldown_seconds = int(rule.cooldown_seconds or 0)
    if cooldown_seconds <= 0:
        return None
    cooldown_start = now - timedelta(seconds=cooldown_seconds)
    return (
        db.query(AlertIncident)
        .filter(
            AlertIncident.alert_rule_id == rule.ar_id,
            AlertIncident.triggered_at >= cooldown_start,
        )
        .order_by(AlertIncident.triggered_at.desc(), AlertIncident.ai_id.desc())
        .first()
    )


def _matching_decisions(
    db: Any,
    *,
    o_id: int,
    outcome: str,
    window_start: datetime,
    window_end: datetime,
    exclude_incident_id: int | None = None,
) -> list[EvaluationDecision]:
    query = db.query(EvaluationDecision).filter(
        EvaluationDecision.o_id == o_id,
        EvaluationDecision.served.is_(True),
        EvaluationDecision.decision_type == "served",
        EvaluationDecision.is_current.is_(True),
        EvaluationDecision.resolved_outcome == outcome,
        EvaluationDecision.evaluated_at >= window_start,
        EvaluationDecision.evaluated_at <= window_end,
    )
    if exclude_incident_id is not None:
        query = query.filter(
            ~exists().where(
                (AlertIncidentCase.alert_incident_id == exclude_incident_id)
                & (AlertIncidentCase.evaluation_decision_id == EvaluationDecision.ed_id)
            )
        )
    return list(query.order_by(EvaluationDecision.ed_id.asc()).all())


def _count_matching_decisions(db: Any, *, o_id: int, outcome: str, window_start: datetime, window_end: datetime) -> int:
    return int(
        db.query(EvaluationDecision.ed_id)
        .filter(
            EvaluationDecision.o_id == o_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
            EvaluationDecision.is_current.is_(True),
            EvaluationDecision.resolved_outcome == outcome,
            EvaluationDecision.evaluated_at >= window_start,
            EvaluationDecision.evaluated_at <= window_end,
        )
        .count()
    )


def _link_incident_to_cases(
    db: Any,
    *,
    incident: AlertIncident,
    rule: AlertRule,
    decisions: list[EvaluationDecision],
) -> list[int]:
    case_ids: list[int] = []
    for decision in decisions:
        result = ensure_case_for_decision(
            db,
            o_id=int(incident.o_id),
            evaluation_decision_id=int(decision.ed_id),
        )
        if result.case_id is None:
            continue
        inserted_link_id = db.execute(
            pg_insert(AlertIncidentCase)
            .values(
                o_id=int(incident.o_id),
                alert_incident_id=int(incident.ai_id),
                case_id=result.case_id,
                evaluation_decision_id=int(decision.ed_id),
                created_at=_utcnow(),
            )
            .on_conflict_do_nothing(
                index_elements=[AlertIncidentCase.alert_incident_id, AlertIncidentCase.evaluation_decision_id]
            )
            .returning(AlertIncidentCase.aic_id)
        ).scalar_one_or_none()
        if inserted_link_id is None:
            case_ids.append(result.case_id)
            continue
        case = db.query(Case).filter(Case.o_id == incident.o_id, Case.case_id == result.case_id).one()
        record_case_event(
            db,
            case=case,
            event_type="alert_linked",
            source_ed_id=int(decision.ed_id),
            details={
                "alert_incident_id": int(incident.ai_id),
                "alert_rule_id": int(rule.ar_id),
                "alert_rule_name": str(rule.name),
                "outcome": str(incident.outcome),
                "observed_count": int(incident.observed_count),
                "threshold": int(incident.threshold),
                "window_start": incident.window_start.isoformat(),
                "window_end": incident.window_end.isoformat(),
            },
        )
        case_ids.append(result.case_id)
    return case_ids


def detect_alerts_for_outcome(db: Any, *, o_id: int, outcome: str, now: datetime | None = None) -> list[int]:
    if not outcome:
        return []

    checked_at = now or _utcnow()
    normalized_outcome = outcome.strip().upper()
    rules = (
        db.query(AlertRule)
        .filter(
            AlertRule.o_id == o_id,
            AlertRule.enabled.is_(True),
            AlertRule.outcome == normalized_outcome,
        )
        .all()
    )
    incident_ids: list[int] = []

    for rule in rules:
        window_end = checked_at
        window_start = window_end - timedelta(seconds=int(rule.window_seconds))
        observed_count = _count_matching_decisions(
            db,
            o_id=o_id,
            outcome=normalized_outcome,
            window_start=window_start,
            window_end=window_end,
        )
        if observed_count <= int(rule.threshold):
            continue
        active_incident = _incident_in_cooldown(db, rule, checked_at)
        if active_incident is not None:
            active_incident.observed_count = observed_count
            active_incident.window_start = window_start
            active_incident.window_end = window_end
            db.flush()
            decisions = _matching_decisions(
                db,
                o_id=o_id,
                outcome=normalized_outcome,
                window_start=window_start,
                window_end=window_end,
                exclude_incident_id=int(active_incident.ai_id),
            )
            _link_incident_to_cases(db, incident=active_incident, rule=rule, decisions=decisions)
            db.commit()
            continue

        decisions = _matching_decisions(
            db,
            o_id=o_id,
            outcome=normalized_outcome,
            window_start=window_start,
            window_end=window_end,
        )

        incident = AlertIncident(
            o_id=o_id,
            alert_rule_id=int(rule.ar_id),
            outcome=normalized_outcome,
            observed_count=observed_count,
            threshold=int(rule.threshold),
            window_start=window_start,
            window_end=window_end,
            dedupe_key=_dedupe_key(rule, window_end),
            severity="critical",
            status="open",
            triggered_at=checked_at,
        )
        db.add(incident)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing_incident = (
                db.query(AlertIncident)
                .filter(
                    AlertIncident.alert_rule_id == rule.ar_id,
                    AlertIncident.dedupe_key == _dedupe_key(rule, window_end),
                )
                .first()
            )
            if existing_incident is not None:
                _link_incident_to_cases(db, incident=existing_incident, rule=rule, decisions=decisions)
                db.commit()
            continue

        case_ids = _link_incident_to_cases(db, incident=incident, rule=rule, decisions=decisions)

        message = NotificationMessage(
            title=f"{normalized_outcome} spike detected",
            body=(
                f"{observed_count} {normalized_outcome} decisions in the last {int(rule.window_seconds // 60)} minutes."
            ),
            severity="critical",
            source_type="alert_incident",
            source_id=int(incident.ai_id),
            action_url=f"/cases?alert_incident_id={incident.ai_id}" if case_ids else "/alerts",
            metadata={
                "outcome": normalized_outcome,
                "observed_count": observed_count,
                "threshold": int(rule.threshold),
                "window_seconds": int(rule.window_seconds),
                "case_ids": case_ids,
            },
        )
        dispatch_notification(
            db,
            o_id=o_id,
            alert_rule_id=int(rule.ar_id),
            incident_id=int(incident.ai_id),
            message=message,
        )
        db.commit()
        incident_ids.append(int(incident.ai_id))

    return incident_ids


def detect_alerts_for_decision(db: Any, *, o_id: int, evaluation_decision_id: int) -> list[int]:
    decision = (
        db.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == o_id, EvaluationDecision.ed_id == evaluation_decision_id)
        .first()
    )
    if decision is None or not decision.resolved_outcome:
        return []
    return detect_alerts_for_outcome(db, o_id=o_id, outcome=str(decision.resolved_outcome))


def sweep_alert_rules(db: Any) -> dict[str, int]:
    outcomes = db.query(AlertRule.o_id, AlertRule.outcome).filter(AlertRule.enabled.is_(True)).distinct().all()
    incidents = 0
    checked = 0
    for o_id, outcome in outcomes:
        checked += 1
        incidents += len(detect_alerts_for_outcome(db, o_id=int(o_id), outcome=str(outcome)))
    return {"checked": checked, "incidents": incidents}


def enqueue_alert_detection(*, o_id: int, evaluation_decision_id: int, resolved_outcome: str | None) -> None:
    if not resolved_outcome:
        return

    if app_settings.TESTING:
        from ezrules.models.database import db_session

        detect_alerts_for_decision(db_session, o_id=o_id, evaluation_decision_id=evaluation_decision_id)
        return

    try:
        from ezrules.backend.tasks import detect_alerts_for_decision_task

        detect_alerts_for_decision_task.delay(o_id, evaluation_decision_id)
    except Exception:
        logger.exception(
            "Failed to enqueue alert detection for org_id=%s evaluation_decision_id=%s",
            o_id,
            evaluation_decision_id,
        )
