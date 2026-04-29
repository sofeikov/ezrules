import datetime
import hashlib
import json
from typing import Any

from ezrules.models.backend_core import EvaluationDecision, EvaluationRuleResult, EventVersion, EventVersionLabel, Label


def _hash_payload(event_data: dict[str, Any]) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def add_served_decision(
    session,
    *,
    org_id: int,
    event_id: str,
    event_data: dict[str, Any],
    event_timestamp: int | None = None,
    evaluated_at: datetime.datetime | None = None,
    outcome_counters: dict[str, int] | None = None,
    resolved_outcome: str | None = None,
    rule_results: dict[int, str] | None = None,
    label: Label | None = None,
) -> EvaluationDecision:
    latest = (
        session.query(EventVersion.event_version)
        .filter(EventVersion.o_id == org_id, EventVersion.event_id == event_id)
        .order_by(EventVersion.event_version.desc())
        .first()
    )
    event_version = int(latest.event_version) + 1 if latest is not None else 1
    timestamp = event_timestamp if event_timestamp is not None else int(datetime.datetime.now(datetime.UTC).timestamp())
    version = EventVersion(
        o_id=org_id,
        event_id=event_id,
        event_version=event_version,
        event_timestamp=timestamp,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
    )
    session.add(version)
    session.flush()

    decision = EvaluationDecision(
        ev_id=int(version.ev_id),
        o_id=org_id,
        event_id=event_id,
        event_version=event_version,
        event_timestamp=timestamp,
        decision_type="served",
        served=True,
        rule_config_label="production",
        outcome_counters=outcome_counters or {},
        resolved_outcome=resolved_outcome,
        all_rule_results={str(r_id): outcome for r_id, outcome in (rule_results or {}).items()},
        evaluated_at=evaluated_at or datetime.datetime.now(datetime.UTC),
    )
    session.add(decision)
    session.flush()

    for r_id, outcome in (rule_results or {}).items():
        session.add(EvaluationRuleResult(ed_id=int(decision.ed_id), r_id=int(r_id), rule_result=str(outcome)))

    if label is not None:
        session.add(EventVersionLabel(o_id=org_id, ev_id=int(version.ev_id), el_id=int(label.el_id)))

    session.flush()
    return decision
