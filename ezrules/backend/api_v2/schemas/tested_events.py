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
    metadata_source: str = Field(
        default="evaluation_snapshot",
        description="Whether rule metadata came from the stored evaluation snapshot or a current-rule fallback",
    )
    referenced_fields: list[str] | None = Field(
        default=None,
        description="Canonical dotted event fields referenced by the rule logic",
    )


class TestedEventItem(BaseModel):
    """Stored event evaluation with the rules that fired."""

    evaluation_decision_id: int = Field(..., description="Immutable served-decision ledger identifier")
    transaction_id: str = Field(..., description="Stable transaction identifier")
    effective_at: str = Field(..., description="When this transaction version became true in the source system")
    observed_at: str = Field(..., description="When this transaction version was observed")
    first_effective_at: str = Field(..., description="Earliest effective time ever seen for this transaction")
    first_observed_at: str = Field(..., description="Earliest observed time ever seen for this transaction")
    event_version: int = Field(..., description="Append-only transaction version number")
    is_current: bool = Field(..., description="Whether this evaluation is the current transaction projection")
    resolved_outcome: str | None = Field(None, description="Winning outcome after severity resolution")
    label_name: str | None = Field(None, description="Uploaded event label applied to the stored event")
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


class TestedEventGraphNode(BaseModel):
    """Node in an event relationship graph."""

    id: str
    kind: str = Field(..., description="Node kind: event or entity")
    label: str
    entity_type: str | None = None
    entity_value: str | None = None
    entity_value_hash: str | None = None
    transaction_id: str | None = None
    event_version: int | None = None
    effective_at: str | None = None
    root: bool = False
    expandable: bool = False


class TestedEventGraphEdge(BaseModel):
    """Relationship between an event node and an entity node."""

    id: str
    source: str
    target: str
    label: str | None = None
    field_path: str | None = None


class TestedEventGraphResponse(BaseModel):
    """Bounded graph around a tested event or expanded entity."""

    nodes: list[TestedEventGraphNode]
    edges: list[TestedEventGraphEdge]
    root_event_node_id: str
    max_events: int
    max_hops: int
    event_count: int
    truncated: bool = False
