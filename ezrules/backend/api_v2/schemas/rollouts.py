"""
Pydantic schemas for rollout deployment API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class RolloutDeployRequest(BaseModel):
    logic: str | None = None
    description: str | None = None
    traffic_percent: int = Field(..., ge=1, le=100)


class RolloutDeployResponse(BaseModel):
    success: bool
    message: str
    error: str | None = None


class RolloutRuleItem(BaseModel):
    r_id: int
    rid: str
    description: str
    logic: str
    traffic_percent: int


class RolloutConfigResponse(BaseModel):
    rules: list[RolloutRuleItem]
    version: int


class RolloutResultItem(BaseModel):
    dr_id: int
    tl_id: int
    r_id: int
    selected_variant: str
    traffic_percent: int | None
    bucket: int | None
    control_result: str | None
    candidate_result: str | None
    returned_result: str | None
    event_id: str
    event_timestamp: int
    created_at: datetime | None


class RolloutResultsResponse(BaseModel):
    results: list[RolloutResultItem]
    total: int


class RolloutOutcomeCount(BaseModel):
    outcome: str
    count: int


class RolloutRuleStatsItem(BaseModel):
    r_id: int
    traffic_percent: int
    total: int
    served_candidate: int
    served_control: int
    candidate_outcomes: list[RolloutOutcomeCount]
    control_outcomes: list[RolloutOutcomeCount]


class RolloutStatsResponse(BaseModel):
    rules: list[RolloutRuleStatsItem]
