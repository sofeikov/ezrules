import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, field_validator

from ezrules.core.outcomes import DatabaseOutcome
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    TestingRecordLog,
    TestingResultsLog,
)


class Event(BaseModel):
    event_id: str
    event_timestamp: int  # Assuming Unix timestamp as input
    event_data: dict

    @field_validator("event_timestamp", mode="before")
    def validate_unix_timestamp(cls, value):
        # Ensure the timestamp is an integer
        if not isinstance(value, int):
            raise ValueError("Timestamp must be an integer")

        # Ensure the timestamp is in a reasonable range (e.g., 1970-01-01 to 3000-01-01)
        min_timestamp = 0  # Unix timestamp for 1970-01-01T00:00:00Z
        max_timestamp = 32503680000  # Approximate Unix timestamp for 3000-01-01T00:00:00Z
        if not (min_timestamp <= value <= max_timestamp):
            raise ValueError("Timestamp out of range")

        return value


def _hash_payload(event_data: dict) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _next_event_version(db_session, o_id: int, event_id: str) -> tuple[int, int | None]:
    latest = (
        db_session.query(EventVersion.ev_id, EventVersion.event_version)
        .filter(EventVersion.o_id == o_id, EventVersion.event_id == event_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    if latest is None:
        return 1, None
    return int(latest.event_version) + 1, int(latest.ev_id)


def eval_and_store(lre, event: Event, response: dict | None = None, commit: bool = True):
    if response is None:
        response = lre.evaluate_rules(event.event_data)
    response, tl_id = store_eval_result(
        db_session=lre.db,
        o_id=lre.o_id,
        event=event,
        response=response,
        rule_config_label=getattr(lre, "label", "production"),
        rule_config_version=getattr(lre, "_current_rule_version", None),
        runtime_config={"execution_mode": getattr(lre, "execution_mode", None)},
        commit=commit,
    )
    return response, tl_id


def store_eval_result(
    db_session,
    o_id: int,
    event: Event,
    response: dict,
    commit: bool = True,
    *,
    decision_type: str = "served",
    served: bool = True,
    idempotency_key: str | None = None,
    rule_config_label: str = "production",
    rule_config_version: int | None = None,
    runtime_config: dict | None = None,
):
    outcome_manager = DatabaseOutcome(db_session=db_session, o_id=o_id)
    created_at_datetime = datetime.fromtimestamp(event.event_timestamp)
    event_version, supersedes_ev_id = _next_event_version(db_session, o_id, event.event_id)
    event_version_record = EventVersion(
        o_id=o_id,
        event_id=event.event_id,
        event_version=event_version,
        event_timestamp=event.event_timestamp,
        event_data=event.event_data,
        payload_hash=_hash_payload(event.event_data),
        supersedes_ev_id=supersedes_ev_id,
    )
    db_session.add(event_version_record)
    db_session.flush()

    tl = TestingRecordLog(
        o_id=o_id,
        event=event.event_data,
        event_timestamp=event.event_timestamp,
        event_id=event.event_id,
        created_at=created_at_datetime,
    )
    db_session.add(tl)
    db_session.flush()

    resolved_outcome = outcome_manager.resolve_outcome(response["outcome_counters"])
    tl.outcome_counters = response["outcome_counters"]
    tl.resolved_outcome = resolved_outcome
    decision = EvaluationDecision(
        ev_id=int(event_version_record.ev_id),
        tl_id=int(tl.tl_id),
        o_id=o_id,
        event_id=event.event_id,
        event_version=event_version,
        event_timestamp=event.event_timestamp,
        decision_type=decision_type,
        served=served,
        idempotency_key=idempotency_key,
        rule_config_label=rule_config_label,
        rule_config_version=rule_config_version,
        runtime_config=runtime_config,
        outcome_counters=response["outcome_counters"],
        resolved_outcome=resolved_outcome,
        all_rule_results=response.get("all_rule_results"),
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(decision)
    db_session.flush()

    for r_id, result in response["rule_results"].items():
        trl = TestingResultsLog(tl_id=tl.tl_id, r_id=r_id, rule_result=result)
        db_session.add(trl)
        db_session.add(EvaluationRuleResult(ed_id=int(decision.ed_id), r_id=int(r_id), rule_result=str(result)))
    response["resolved_outcome"] = resolved_outcome
    response["event_version"] = event_version
    response["event_version_id"] = int(event_version_record.ev_id)
    response["evaluation_decision_id"] = int(decision.ed_id)
    if commit:
        db_session.commit()
    return response, tl.tl_id
