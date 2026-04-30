"""
Pydantic schemas for the evaluator endpoint.

These schemas define the request/response format for event evaluation.
"""

from pydantic import BaseModel, Field, field_validator


class EvaluateRequest(BaseModel):
    """Schema for evaluating an event against the rule engine."""

    event_id: str = Field(..., description="Unique identifier for the event")
    event_timestamp: int = Field(..., description="Unix timestamp for the event")
    event_data: dict = Field(..., description="Event payload to evaluate against rules")

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def validate_unix_timestamp(cls, value: int) -> int:
        if not isinstance(value, int):
            raise ValueError("Timestamp must be an integer")
        min_timestamp = 0
        max_timestamp = 32503680000  # ~3000-01-01
        if not (min_timestamp <= value <= max_timestamp):
            raise ValueError("Timestamp out of range")
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "event_id": "evt_123456",
                "event_timestamp": 1700000000,
                "event_data": {"amount": 500.25, "country": "US"},
            }
        }
    }


class EvaluateResponse(BaseModel):
    """Response from rule evaluation."""

    outcome_counters: dict[str, int] = Field(..., description="Count of each outcome type across all rules")
    outcome_set: list[str] = Field(..., description="Unique set of outcomes produced")
    resolved_outcome: str | None = Field(
        None, description="Highest-severity outcome after applying the configured hierarchy"
    )
    rule_results: dict[str, str] = Field(..., description="Mapping of rule_id to its outcome")
    event_version: int | None = Field(None, description="Canonical append-only version for this business event")
    evaluation_decision_id: int | None = Field(None, description="Immutable served-decision ledger identifier")


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
