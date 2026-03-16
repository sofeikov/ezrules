"""
Pydantic schemas for tested-event API endpoints.
"""

from pydantic import BaseModel, Field


class TriggeredRuleItem(BaseModel):
    """Rule that produced an outcome for a stored event."""

    r_id: int = Field(..., description="Internal rule identifier")
    rid: str = Field(..., description="Stable rule identifier")
    description: str = Field(..., description="Rule description")
    outcome: str = Field(..., description="Outcome returned by the rule")
    referenced_fields: list[str] | None = Field(
        default=None,
        description="Top-level event fields referenced by the rule logic",
    )


class TestedEventItem(BaseModel):
    """Stored event evaluation with the rules that fired."""

    tl_id: int = Field(..., description="Stored tested-event identifier")
    event_id: str = Field(..., description="External event identifier")
    event_timestamp: int = Field(..., description="Original event timestamp as a Unix integer")
    resolved_outcome: str | None = Field(None, description="Winning outcome after severity resolution")
    outcome_counters: dict[str, int] = Field(default_factory=dict, description="Counts of rule outcomes for the event")
    event_data: dict = Field(..., description="Original event payload")
    triggered_rules: list[TriggeredRuleItem] = Field(
        default_factory=list,
        description="Rules that returned an outcome for the event",
    )


class TestedEventsResponse(BaseModel):
    """Response for listing recent tested events."""

    events: list[TestedEventItem]
    total: int
    limit: int
