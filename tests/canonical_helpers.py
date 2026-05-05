import datetime
import hashlib
import json
from typing import Any

from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    EventVersionLabel,
    Label,
    TransactionCurrentVersion,
)


def _hash_payload(event_data: dict[str, Any]) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _min_utc(left: datetime.datetime, right: datetime.datetime) -> datetime.datetime:
    left_utc = _as_utc(left)
    right_utc = _as_utc(right)
    return left_utc if left_utc <= right_utc else right_utc


def add_served_decision(
    session,
    *,
    org_id: int,
    transaction_id: str,
    event_data: dict[str, Any],
    effective_at: int | None = None,
    evaluated_at: datetime.datetime | None = None,
    outcome_counters: dict[str, int] | None = None,
    resolved_outcome: str | None = None,
    rule_results: dict[int, str] | None = None,
    label: Label | None = None,
) -> EvaluationDecision:
    latest = (
        session.query(EventVersion.event_version)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc())
        .first()
    )
    event_version = int(latest.event_version) + 1 if latest is not None else 1
    timestamp = effective_at if effective_at is not None else int(datetime.datetime.now(datetime.UTC).timestamp())
    effective_dt = datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
    version = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=event_version,
        effective_at=effective_dt,
        observed_at=effective_dt,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
        terminal_state=False,
    )
    session.add(version)
    session.flush()

    decision = EvaluationDecision(
        ev_id=int(version.ev_id),
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=event_version,
        effective_at=effective_dt,
        observed_at=effective_dt,
        decision_type="served",
        served=True,
        is_current=True,
        rule_config_label="production",
        outcome_counters=outcome_counters or {},
        resolved_outcome=resolved_outcome,
        all_rule_results={str(r_id): outcome for r_id, outcome in (rule_results or {}).items()},
        evaluated_at=evaluated_at or datetime.datetime.now(datetime.UTC),
    )
    session.add(decision)
    session.flush()

    current = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == org_id, TransactionCurrentVersion.transaction_id == transaction_id)
        .first()
    )
    if current is not None:
        previous_decision = (
            session.query(EvaluationDecision)
            .filter(EvaluationDecision.o_id == org_id, EvaluationDecision.ed_id == current.current_ed_id)
            .first()
        )
        if previous_decision is not None:
            previous_decision.is_current = False
            previous_decision.superseded_by_ed_id = int(decision.ed_id)
            previous_decision.superseded_at = datetime.datetime.now(datetime.UTC)
        current.current_ev_id = int(version.ev_id)
        current.current_ed_id = int(decision.ed_id)
        current.first_effective_at = _min_utc(current.first_effective_at, effective_dt)
        current.first_observed_at = _min_utc(current.first_observed_at, effective_dt)
        current.current_effective_at = effective_dt
        current.current_observed_at = effective_dt
        current.updated_at = datetime.datetime.now(datetime.UTC)
    else:
        session.add(
            TransactionCurrentVersion(
                o_id=org_id,
                transaction_id=transaction_id,
                current_ev_id=int(version.ev_id),
                current_ed_id=int(decision.ed_id),
                first_effective_at=effective_dt,
                first_observed_at=effective_dt,
                current_effective_at=effective_dt,
                current_observed_at=effective_dt,
                terminal_state=False,
                updated_at=datetime.datetime.now(datetime.UTC),
            )
        )

    for r_id, outcome in (rule_results or {}).items():
        session.add(EvaluationRuleResult(ed_id=int(decision.ed_id), r_id=int(r_id), rule_result=str(outcome)))

    if label is not None:
        session.add(EventVersionLabel(o_id=org_id, ev_id=int(version.ev_id), el_id=int(label.el_id)))

    session.flush()
    return decision
