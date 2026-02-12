from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    r_id: int = Field(..., description="ID of the rule to backtest")
    new_rule_logic: str = Field(..., min_length=1, description="Proposed new rule logic to compare against")


class BacktestTriggerResponse(BaseModel):
    success: bool
    task_id: str = Field(default="", description="Celery task ID for tracking")
    message: str
    error: str | None = None


class BacktestResultItem(BaseModel):
    task_id: str
    created_at: datetime | None = None
    stored_logic: str | None = None
    proposed_logic: str | None = None

    model_config = {"from_attributes": True}


class BacktestResultsResponse(BaseModel):
    results: list[BacktestResultItem]


class BacktestTaskResult(BaseModel):
    status: str
    stored_result: dict[str, int] | None = None
    proposed_result: dict[str, int] | None = None
    stored_result_rate: dict[str, float] | None = None
    proposed_result_rate: dict[str, float] | None = None
    total_records: int | None = None
    error: str | None = None
