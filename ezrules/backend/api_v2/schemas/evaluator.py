"""
Pydantic schemas for the evaluator endpoint.

These schemas define the request/response format for event evaluation.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EvaluateRequest(BaseModel):
    """Schema for evaluating an event against the rule engine."""

    transaction_id: str = Field(..., description="Stable identifier for the real-world transaction")
    effective_at: datetime = Field(..., description="When this transaction version became true in the source system")
    observed_at: datetime | None = Field(None, description="When ezrules or the caller observed this version")
    terminal_state: bool = Field(False, description="Whether this version closes the transaction lifecycle")
    event_data: dict = Field(..., description="Event payload to evaluate against rules")

    @field_validator("effective_at", "observed_at", mode="before")
    @classmethod
    def validate_timestamp(cls, value):
        if value is None:
            return value
        if isinstance(value, int):
            min_timestamp = 0
            max_timestamp = 32503680000  # ~3000-01-01
            if not (min_timestamp <= value <= max_timestamp):
                raise ValueError("Timestamp out of range")
            return datetime.fromtimestamp(value, UTC)
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "txn_123456",
                "effective_at": "2026-04-23T12:00:00Z",
                "observed_at": "2026-04-23T12:00:03Z",
                "event_data": {"amount": 500.25, "country": "US"},
            }
        }
    }


class EvaluateResponse(BaseModel):
    """Response from rule evaluation."""

    transaction_id: str = Field(..., description="Stable identifier for the real-world transaction")
    outcome_counters: dict[str, int] = Field(..., description="Count of each outcome type across all rules")
    outcome_set: list[str] = Field(..., description="Unique set of outcomes produced")
    resolved_outcome: str | None = Field(
        None, description="Highest-severity outcome after applying the configured hierarchy"
    )
    rule_results: dict[str, str] = Field(..., description="Mapping of rule_id to its outcome")
    event_version: int | None = Field(None, description="Canonical append-only version for this business event")
    event_version_id: int | None = Field(None, description="Immutable event-version ledger identifier")
    evaluation_id: int | None = Field(None, description="Immutable served-decision ledger identifier")
    evaluation_status: Literal["new", "duplicate", "superseding"] = Field(
        "new",
        description="Whether this request created a first/non-current version, reused an existing version, or superseded current truth",
    )
    is_current: bool | None = Field(None, description="Whether this evaluation is the current transaction projection")
    superseded_evaluation_id: int | None = Field(None, description="Evaluation that superseded this one, when known")


class EventTestRuleResult(BaseModel):
    """Rule result details returned by a dry-run event test."""

    r_id: int = Field(..., description="Internal numeric rule identifier")
    rid: str = Field(..., description="External rule identifier")
    description: str = Field(..., description="Rule description")
    evaluation_lane: str = Field(..., description="Rule evaluation lane")
    outcome: str | None = Field(None, description="Outcome returned by the rule, if any")
    matched: bool = Field(..., description="Whether the rule returned an outcome")


class EventTestResponse(EvaluateResponse):
    """Response from a non-persistent rule-set event test."""

    dry_run: bool = Field(True, description="Always true for event test responses")
    skipped_main_rules: bool = Field(False, description="Whether allowlist rules short-circuited main rule evaluation")
    all_rule_results: dict[str, str | None] = Field(
        default_factory=dict,
        description="Mapping of evaluated rule IDs to their outcome, including non-matches",
    )
    evaluated_rules: list[EventTestRuleResult] = Field(
        default_factory=list,
        description="Metadata for all rules evaluated during the dry run",
    )
