from typing import Any

from pydantic import BaseModel, Field


class AgentToolEvidenceEvent(BaseModel):
    transaction_id: str
    event_version: int
    evaluation_decision_id: int
    label_name: str | None = None
    stored_outcome: str | None = None
    proposed_outcome: str | None = None
    group: dict[str, Any] = Field(default_factory=dict)
    event_data: dict[str, Any] = Field(default_factory=dict)


class AgentToolGroupDelta(BaseModel):
    group: dict[str, Any]
    total_records: int
    changed_decision_count: int
    changed_decision_rate: float
    stored_result: dict[str, int]
    proposed_result: dict[str, int]
    outcome_delta: dict[str, int]


class RuleBlastRadiusRequest(BaseModel):
    rule_id: int = Field(..., description="Existing rule ID to compare against")
    proposed_logic: str = Field(..., min_length=1, description="Candidate rule logic")
    lookback_days: int = Field(default=30, ge=1, le=365)
    group_by: list[str] = Field(default_factory=list, max_length=5)
    sample_limit: int = Field(default=20, ge=1, le=100)
    max_records: int = Field(default=10_000, ge=1, le=100_000)


class RuleBlastRadiusResponse(BaseModel):
    rule_id: int
    lookback_days: int
    total_records: int
    eligible_records: int
    skipped_records: int
    stored_result: dict[str, int]
    proposed_result: dict[str, int]
    outcome_delta: dict[str, int]
    changed_decision_count: int
    changed_decision_rate: float
    group_deltas: list[AgentToolGroupDelta]
    flipped_events: list[AgentToolEvidenceEvent]
    warnings: list[str] = Field(default_factory=list)


class RuleCounterexamplesRequest(BaseModel):
    rule_id: int = Field(..., description="Existing rule ID to inspect")
    proposed_logic: str | None = Field(default=None, description="Optional candidate logic for fix/regression buckets")
    lookback_days: int = Field(default=30, ge=1, le=365)
    positive_labels: list[str] = Field(default_factory=lambda: ["FRAUD"])
    negative_labels: list[str] = Field(default_factory=lambda: ["NORMAL", "LEGIT", "GENUINE"])
    target_outcomes: list[str] | None = Field(
        default=None,
        description="Optional outcome names that count as an actionable rule fire",
    )
    sample_limit: int = Field(default=20, ge=1, le=100)
    max_records: int = Field(default=10_000, ge=1, le=100_000)


class RuleCounterexampleBuckets(BaseModel):
    fired_but_negative: list[AgentToolEvidenceEvent]
    missed_positive: list[AgentToolEvidenceEvent]
    candidate_fixes_existing: list[AgentToolEvidenceEvent]
    candidate_introduces_new_errors: list[AgentToolEvidenceEvent]


class RuleCounterexamplesResponse(BaseModel):
    rule_id: int
    lookback_days: int
    total_records: int
    eligible_records: int
    skipped_records: int
    positive_labels: list[str]
    negative_labels: list[str]
    target_outcomes: list[str] | None = None
    buckets: RuleCounterexampleBuckets
    warnings: list[str] = Field(default_factory=list)
