import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError

from ezrules.backend.notifications import NotificationMessage, dispatch_notification
from ezrules.models.backend_core import AlertIncident, AlertRule, EvaluationDecision
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dedupe_key(rule: AlertRule, window_end: datetime) -> str:
    bucket_seconds = max(int(rule.cooldown_seconds or 0), 60)
    bucket = int(window_end.timestamp()) // bucket_seconds
    return f"rule:{rule.ar_id}:outcome:{rule.outcome}:bucket:{bucket}"


def _cooldown_allows_incident(db: Any, rule: AlertRule, now: datetime) -> bool:
    cooldown_seconds = int(rule.cooldown_seconds or 0)
    if cooldown_seconds <= 0:
        return True
    cooldown_start = now - timedelta(seconds=cooldown_seconds)
    existing = (
        db.query(AlertIncident.ai_id)
        .filter(
            AlertIncident.alert_rule_id == rule.ar_id,
            AlertIncident.triggered_at >= cooldown_start,
        )
        .first()
    )
    return existing is None


def _count_matching_decisions(db: Any, *, o_id: int, outcome: str, window_start: datetime, window_end: datetime) -> int:
    return int(
        db.query(EvaluationDecision)
        .filter(
            EvaluationDecision.o_id == o_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
            EvaluationDecision.resolved_outcome == outcome,
            EvaluationDecision.evaluated_at >= window_start,
            EvaluationDecision.evaluated_at <= window_end,
        )
        .count()
    )


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
        if not _cooldown_allows_incident(db, rule, checked_at):
            continue

        incident = AlertIncident(
            o_id=o_id,
            alert_rule_id=int(rule.ar_id),
            outcome=normalized_outcome,
            observed_count=observed_count,
            threshold=int(rule.threshold),
            window_start=window_start,
            window_end=window_end,
            dedupe_key=_dedupe_key(rule, window_end),
            status="open",
            triggered_at=checked_at,
        )
        db.add(incident)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue

        message = NotificationMessage(
            title=f"{normalized_outcome} spike detected",
            body=(
                f"{observed_count} {normalized_outcome} decisions in the last {int(rule.window_seconds // 60)} minutes."
            ),
            severity="critical",
            source_type="alert_incident",
            source_id=int(incident.ai_id),
            action_url="/alerts",
            metadata={
                "outcome": normalized_outcome,
                "observed_count": observed_count,
                "threshold": int(rule.threshold),
                "window_seconds": int(rule.window_seconds),
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
