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
    rule_results: dict[str, str] = Field(..., description="Mapping of rule_id to its outcome")
