import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, field_validator
from sqlalchemy import text

from ezrules.core.outcomes import DatabaseOutcome
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    TransactionCurrentVersion,
)


class Event(BaseModel):
    transaction_id: str
    effective_at: datetime
    event_data: dict
    observed_at: datetime | None = None
    terminal_state: bool = False

    @field_validator("effective_at", "observed_at", mode="before")
    @classmethod
    def validate_timestamp(cls, value):
        if value is None:
            return value
        if isinstance(value, int):
            min_timestamp = 0
            max_timestamp = 32503680000
            if not (min_timestamp <= value <= max_timestamp):
                raise ValueError("Timestamp out of range")
            return datetime.fromtimestamp(value, UTC)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        raise ValueError("Timestamp must be an integer Unix timestamp or datetime")

    @property
    def effective_timestamp(self) -> int:
        return int(self.effective_at.timestamp())

    @property
    def event_timestamp(self) -> int:
        return self.effective_timestamp

    @property
    def event_id(self) -> str:
        return self.transaction_id


def _hash_payload(event_data: dict) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


EvaluationStatus = Literal["new", "duplicate", "superseding"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _next_event_version(db_session, o_id: int, transaction_id: str) -> tuple[int, int | None]:
    latest = (
        db_session.query(EventVersion.ev_id, EventVersion.event_version)
        .filter(EventVersion.o_id == o_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    if latest is None:
        return 1, None
    return int(latest.event_version) + 1, int(latest.ev_id)


def _transaction_lock_key(o_id: int, transaction_id: str) -> int:
    digest = hashlib.sha256(f"{o_id}:{transaction_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) & ((1 << 63) - 1)


def lock_transaction_for_evaluation(db_session, o_id: int, transaction_id: str) -> None:
    """Serialize version/current-projection writes for a single transaction."""
    db_session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _transaction_lock_key(o_id, transaction_id)},
    )


def _load_rule_results(db_session, decision_id: int) -> dict[str, str]:
    rows = (
        db_session.query(EvaluationRuleResult.r_id, EvaluationRuleResult.rule_result)
        .filter(EvaluationRuleResult.ed_id == decision_id)
        .order_by(EvaluationRuleResult.r_id.asc())
        .all()
    )
    return {str(r_id): str(result) for r_id, result in rows}


def build_response_from_decision(
    db_session,
    decision: EvaluationDecision,
    event_version: EventVersion,
    *,
    evaluation_status: EvaluationStatus,
) -> dict[str, Any]:
    raw_outcome_counters = decision.outcome_counters if isinstance(decision.outcome_counters, dict) else {}
    outcome_counters = {str(outcome): int(count) for outcome, count in raw_outcome_counters.items()}
    return {
        "transaction_id": str(decision.transaction_id),
        "outcome_counters": outcome_counters,
        "outcome_set": sorted(outcome_counters.keys()),
        "resolved_outcome": decision.resolved_outcome,
        "rule_results": _load_rule_results(db_session, int(decision.ed_id)),
        "event_version": int(decision.event_version),
        "event_version_id": int(event_version.ev_id),
        "evaluation_id": int(decision.ed_id),
        "evaluation_decision_id": int(decision.ed_id),
        "evaluation_status": evaluation_status,
        "is_current": bool(decision.is_current),
        "superseded_evaluation_id": int(decision.superseded_by_ed_id)
        if decision.superseded_by_ed_id is not None
        else None,
    }


def find_duplicate_evaluation(db_session, o_id: int, event: Event) -> dict[str, Any] | None:
    payload_hash = _hash_payload(event.event_data)
    effective_at = _as_utc(event.effective_at)
    filters = [
        EventVersion.o_id == o_id,
        EventVersion.transaction_id == event.transaction_id,
        EventVersion.payload_hash == payload_hash,
        EventVersion.effective_at == effective_at,
        EventVersion.terminal_state.is_(event.terminal_state),
        EvaluationDecision.served.is_(True),
        EvaluationDecision.decision_type == "served",
    ]
    if event.observed_at is not None:
        filters.append(EventVersion.observed_at == _as_utc(event.observed_at))
    row = (
        db_session.query(EvaluationDecision, EventVersion)
        .join(EventVersion, EventVersion.ev_id == EvaluationDecision.ev_id)
        .filter(*filters)
        .order_by(EvaluationDecision.ed_id.desc())
        .first()
    )
    if row is None:
        return None
    decision, version = row
    return build_response_from_decision(db_session, decision, version, evaluation_status="duplicate")


def _should_be_current(
    current: TransactionCurrentVersion | None,
    *,
    effective_at: datetime,
    observed_at: datetime,
    terminal_state: bool,
) -> bool:
    if current is None:
        return True
    if current.terminal_state:
        return False
    if terminal_state:
        return True
    current_key = (
        _as_utc(cast(datetime, current.current_effective_at)),
        _as_utc(cast(datetime, current.current_observed_at)),
    )
    new_key = (_as_utc(effective_at), _as_utc(observed_at))
    return new_key >= current_key


def _min_utc(left: datetime, right: datetime) -> datetime:
    left_utc = _as_utc(left)
    right_utc = _as_utc(right)
    return left_utc if left_utc <= right_utc else right_utc


def eval_and_store(lre, event: Event, response: dict | None = None, commit: bool = True):
    if response is None:
        response = lre.evaluate_rules(event.event_data)
    response, decision_id = store_eval_result(
        db_session=lre.db,
        o_id=lre.o_id,
        event=event,
        response=response,
        rule_config_label=getattr(lre, "label", "production"),
        rule_config_version=getattr(lre, "_current_rule_version", None),
        runtime_config={"execution_mode": getattr(lre, "execution_mode", None)},
        commit=commit,
    )
    return response, decision_id


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
    lock_transaction_for_evaluation(db_session, o_id, event.transaction_id)
    effective_at = _as_utc(event.effective_at)
    observed_at = _as_utc(event.observed_at or datetime.now(UTC))
    event_version, supersedes_ev_id = _next_event_version(db_session, o_id, event.transaction_id)
    current = (
        db_session.query(TransactionCurrentVersion)
        .filter(
            TransactionCurrentVersion.o_id == o_id, TransactionCurrentVersion.transaction_id == event.transaction_id
        )
        .first()
    )
    becomes_current = _should_be_current(
        current,
        effective_at=effective_at,
        observed_at=observed_at,
        terminal_state=event.terminal_state,
    )
    event_version_record = EventVersion(
        o_id=o_id,
        transaction_id=event.transaction_id,
        event_version=event_version,
        effective_at=effective_at,
        observed_at=observed_at,
        event_data=event.event_data,
        payload_hash=_hash_payload(event.event_data),
        terminal_state=event.terminal_state,
        supersedes_ev_id=supersedes_ev_id,
    )
    db_session.add(event_version_record)
    db_session.flush()

    resolved_outcome = outcome_manager.resolve_outcome(response["outcome_counters"])
    decision = EvaluationDecision(
        ev_id=int(event_version_record.ev_id),
        o_id=o_id,
        transaction_id=event.transaction_id,
        event_version=event_version,
        effective_at=effective_at,
        observed_at=observed_at,
        decision_type=decision_type,
        served=served,
        is_current=becomes_current,
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

    evaluation_status: EvaluationStatus = "new"
    if becomes_current and current is not None:
        previous_decision = (
            db_session.query(EvaluationDecision)
            .filter(EvaluationDecision.o_id == o_id, EvaluationDecision.ed_id == current.current_ed_id)
            .first()
        )
        if previous_decision is not None:
            previous_decision.is_current = False
            previous_decision.superseded_by_ed_id = int(decision.ed_id)
            previous_decision.superseded_at = datetime.now(UTC)
        current.current_ev_id = int(event_version_record.ev_id)
        current.current_ed_id = int(decision.ed_id)
        current.first_effective_at = _min_utc(cast(datetime, current.first_effective_at), effective_at)
        current.first_observed_at = _min_utc(cast(datetime, current.first_observed_at), observed_at)
        current.current_effective_at = effective_at
        current.current_observed_at = observed_at
        current.terminal_state = bool(event.terminal_state)
        current.updated_at = datetime.now(UTC)
        evaluation_status = "superseding"
    elif becomes_current:
        db_session.add(
            TransactionCurrentVersion(
                o_id=o_id,
                transaction_id=event.transaction_id,
                current_ev_id=int(event_version_record.ev_id),
                current_ed_id=int(decision.ed_id),
                first_effective_at=effective_at,
                first_observed_at=observed_at,
                current_effective_at=effective_at,
                current_observed_at=observed_at,
                terminal_state=bool(event.terminal_state),
                updated_at=datetime.now(UTC),
            )
        )
    elif current is not None:
        current.first_effective_at = _min_utc(cast(datetime, current.first_effective_at), effective_at)
        current.first_observed_at = _min_utc(cast(datetime, current.first_observed_at), observed_at)
        current.updated_at = datetime.now(UTC)

    for r_id, result in response["rule_results"].items():
        db_session.add(EvaluationRuleResult(ed_id=int(decision.ed_id), r_id=int(r_id), rule_result=str(result)))
    response["transaction_id"] = event.transaction_id
    response["resolved_outcome"] = resolved_outcome
    response["event_version"] = event_version
    response["event_version_id"] = int(event_version_record.ev_id)
    response["evaluation_id"] = int(decision.ed_id)
    response["evaluation_decision_id"] = int(decision.ed_id)
    response["evaluation_status"] = evaluation_status
    response["is_current"] = bool(decision.is_current)
    response["superseded_evaluation_id"] = None
    if commit:
        db_session.commit()
    return response, int(decision.ed_id)
