"""Response contracts for the operations dashboard MVP."""

import datetime

from pydantic import BaseModel, Field


class OperationsMetrics(BaseModel):
    active_cases: int = Field(..., ge=0)
    unassigned_cases: int = Field(..., ge=0)
    resolved_cases: int = Field(..., ge=0)
    dispositioned_cases: int = Field(..., ge=0)
    false_positive_cases: int = Field(..., ge=0)
    false_positive_rate: float | None = Field(..., ge=0, le=1)


class OperationsCaseFlowPoint(BaseModel):
    date: datetime.date
    opened: int = Field(..., ge=0)
    resolved: int = Field(..., ge=0)


class OperationsAttentionCase(BaseModel):
    case_id: int
    outcome: str | None = None
    assigned_to_email: str | None = None
    age_seconds: int = Field(..., ge=0)


class OperationsNoisyRule(BaseModel):
    rid: str
    description: str
    case_count: int = Field(..., ge=0)
    resolved_count: int = Field(..., ge=0)
    false_positive_count: int = Field(..., ge=0)
    false_positive_rate: float | None = Field(..., ge=0, le=1)


class OperationsSummaryResponse(BaseModel):
    days: int
    period_start: datetime.datetime
    period_end: datetime.datetime
    generated_at: datetime.datetime
    summary: OperationsMetrics
    case_flow: list[OperationsCaseFlowPoint]
    attention_cases: list[OperationsAttentionCase]
    noisy_rules: list[OperationsNoisyRule]
