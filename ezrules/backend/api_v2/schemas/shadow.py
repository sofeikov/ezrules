"""
Pydantic schemas for shadow deployment API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel


class ShadowDeployRequest(BaseModel):
    logic: str | None = None
    description: str | None = None


class ShadowDeployResponse(BaseModel):
    success: bool
    message: str
    error: str | None = None


class ShadowRuleItem(BaseModel):
    r_id: int
    rid: str
    description: str
    logic: str


class ShadowConfigResponse(BaseModel):
    rules: list[ShadowRuleItem]
    version: int


class ShadowResultItem(BaseModel):
    sr_id: int
    tl_id: int
    r_id: int
    rule_result: str
    event_id: str
    event_timestamp: int
    created_at: datetime | None


class ShadowResultsResponse(BaseModel):
    results: list[ShadowResultItem]
    total: int


class ShadowOutcomeCount(BaseModel):
    outcome: str
    count: int


class ShadowRuleStatsItem(BaseModel):
    r_id: int
    total: int
    shadow_outcomes: list[ShadowOutcomeCount]
    prod_outcomes: list[ShadowOutcomeCount]


class ShadowStatsResponse(BaseModel):
    rules: list[ShadowRuleStatsItem]
