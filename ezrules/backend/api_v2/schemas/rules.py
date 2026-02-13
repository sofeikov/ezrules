"""
Pydantic schemas for rule-related API endpoints.

These schemas define the request/response format for the Rules API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class RuleCreate(BaseModel):
    """Schema for creating a new rule."""

    rid: str = Field(..., min_length=1, description="Unique rule identifier (e.g., 'rule_001')")
    description: str = Field(..., min_length=1, description="Human-readable description of what the rule does")
    logic: str = Field(..., min_length=1, description="Rule logic expression")

    model_config = {
        "json_schema_extra": {
            "example": {
                "rid": "high_value_transaction",
                "description": "Flag transactions over $10,000",
                "logic": "event.amount > 10000",
            }
        }
    }


class RuleUpdate(BaseModel):
    """Schema for updating an existing rule.

    All fields are optional - only provided fields will be updated.
    """

    description: str | None = Field(None, description="New description for the rule")
    logic: str | None = Field(None, description="New rule logic expression")


class RuleVerifyRequest(BaseModel):
    """Schema for verifying rule syntax without saving."""

    rule_source: str = Field(..., description="Rule logic expression to verify")


class RuleTestRequest(BaseModel):
    """Schema for testing rule execution against sample data."""

    rule_source: str = Field(..., description="Rule logic expression to test")
    test_json: str = Field(..., description="JSON string of test event data")


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class RuleRevisionSummary(BaseModel):
    """Brief summary of a rule revision (for lists)."""

    revision_number: int
    created_at: datetime | None = None


class RuleResponse(BaseModel):
    """Full rule details returned from API."""

    r_id: int = Field(..., description="Database primary key")
    rid: str = Field(..., description="Rule identifier")
    description: str
    logic: str
    created_at: datetime | None = None
    revisions: list[RuleRevisionSummary] = Field(default_factory=list)
    revision_number: int | None = Field(None, description="Revision number (only for historical revisions)")

    model_config = {"from_attributes": True}


class RuleListItem(BaseModel):
    """Abbreviated rule info for list endpoints."""

    r_id: int
    rid: str
    description: str
    logic: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RulesListResponse(BaseModel):
    """Response for GET /rules endpoint."""

    rules: list[RuleListItem]
    evaluator_endpoint: str | None = None


class RuleHistoryEntry(BaseModel):
    """A single entry in rule history."""

    revision_number: int
    logic: str
    description: str
    created_at: datetime | None = None
    is_current: bool = False


class RuleHistoryResponse(BaseModel):
    """Response for GET /rules/{id}/history endpoint."""

    r_id: int
    rid: str
    history: list[RuleHistoryEntry]


class RuleVerifyResponse(BaseModel):
    """Response for rule verification."""

    params: list[str] = Field(default_factory=list, description="Parameters extracted from the rule")


class RuleTestResponse(BaseModel):
    """Response for rule test execution."""

    status: str = Field(..., description="'ok' or 'error'")
    reason: str
    rule_outcome: str | None = None


class RuleMutationResponse(BaseModel):
    """Response for create/update operations."""

    success: bool
    message: str
    rule: RuleResponse | None = None
    error: str | None = None
