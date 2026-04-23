"""
Pydantic schemas for rule-related API endpoints.

These schemas define the request/response format for the Rules API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from ezrules.models.backend_core import RuleStatus

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class RuleCreate(BaseModel):
    """Schema for creating a new rule."""

    rid: str = Field(..., min_length=1, description="Unique rule identifier (e.g., 'rule_001')")
    description: str = Field(..., min_length=1, description="Human-readable description of what the rule does")
    logic: str = Field(..., min_length=1, description="Rule logic expression")
    execution_order: int | None = Field(default=None, ge=1, description="Execution order for main rules")
    evaluation_lane: str = Field(default="main", description="Evaluation lane: main or allowlist")

    model_config = {
        "json_schema_extra": {
            "example": {
                "rid": "high_value_transaction",
                "description": "Flag transactions over $10,000",
                "logic": "if $amount > 10000:\n\treturn !HOLD",
            }
        }
    }


class RuleUpdate(BaseModel):
    """Schema for updating an existing rule.

    All fields are optional - only provided fields will be updated.
    """

    description: str | None = Field(None, description="New description for the rule")
    logic: str | None = Field(None, description="New rule logic expression")
    execution_order: int | None = Field(None, ge=1, description="Execution order for main rules")
    evaluation_lane: str | None = Field(None, description="Evaluation lane: main or allowlist")


class RuleVerifyRequest(BaseModel):
    """Schema for verifying rule syntax without saving."""

    rule_source: str = Field(..., description="Rule logic expression to verify")


class RuleTestRequest(BaseModel):
    """Schema for testing rule execution against sample data."""

    rule_source: str = Field(..., description="Rule logic expression to test")
    test_json: str = Field(..., description="JSON string of test event data")


class RuleAIDraftRequest(BaseModel):
    """Schema for AI-assisted rule draft generation."""

    prompt: str = Field(..., min_length=1, description="Natural-language request describing the desired rule")
    evaluation_lane: str = Field(default="main", description="Evaluation lane: main or allowlist")
    mode: str = Field(..., description="Authoring mode: create or edit")
    current_logic: str | None = Field(default=None, description="Existing rule logic used as edit context")
    current_description: str | None = Field(default=None, description="Existing rule description used as edit context")
    rule_id: int | None = Field(default=None, description="Existing rule ID when generating from the edit flow")


class RuleAIDraftApplyRequest(BaseModel):
    """Schema for recording that an AI draft was explicitly applied in the editor."""

    generation_id: str = Field(..., min_length=1, description="Generation identifier returned from /ai/draft")
    rule_id: int | None = Field(default=None, description="Rule ID when applying from the rule detail edit flow")


class RuleRollbackRequest(BaseModel):
    """Schema for rolling a rule back to a historical revision."""

    revision_number: int = Field(..., ge=1, description="Historical revision number to restore")


class MainRuleOrderUpdateRequest(BaseModel):
    """Replace the full ordered main-rule sequence."""

    ordered_r_ids: list[int] = Field(
        default_factory=list,
        description="Main rule IDs ordered from earliest to latest execution",
    )


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
    execution_order: int = Field(..., ge=1, description="Execution order used for main-rule evaluation")
    evaluation_lane: str = Field(..., description="Evaluation lane for this rule")
    status: RuleStatus = Field(..., description="Rule lifecycle status")
    effective_from: datetime | None = Field(None, description="When the currently active version became effective")
    approved_by: int | None = Field(None, description="User ID that approved promotion to active")
    approved_at: datetime | None = Field(None, description="When the rule was approved for activation")
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
    execution_order: int = Field(..., ge=1, description="Execution order used for main-rule evaluation")
    evaluation_lane: str = Field(..., description="Evaluation lane for this rule")
    status: RuleStatus = Field(..., description="Rule lifecycle status")
    effective_from: datetime | None = Field(None, description="When the currently active version became effective")
    approved_by: int | None = Field(None, description="User ID that approved promotion to active")
    approved_at: datetime | None = Field(None, description="When the rule was approved for activation")
    created_at: datetime | None = None
    in_shadow: bool = False
    in_rollout: bool = False
    rollout_percent: int | None = None

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
    execution_order: int = Field(..., ge=1, description="Execution order captured in this revision")
    evaluation_lane: str = Field(..., description="Evaluation lane for this revision")
    status: RuleStatus = Field(..., description="Rule lifecycle status in this revision")
    effective_from: datetime | None = Field(None, description="When this revision became effective")
    approved_by: int | None = Field(None, description="User ID that approved this revision")
    approved_at: datetime | None = Field(None, description="When this revision was approved")
    created_at: datetime | None = None
    is_current: bool = False


class RuleHistoryResponse(BaseModel):
    """Response for GET /rules/{id}/history endpoint."""

    r_id: int
    rid: str
    history: list[RuleHistoryEntry]


class RuleVerifyError(BaseModel):
    """Structured validation error returned while verifying rule logic."""

    message: str = Field(..., description="Human-readable validation failure")
    line: int | None = Field(default=None, description="1-based line number where the error starts")
    column: int | None = Field(default=None, description="1-based column number where the error starts")
    end_line: int | None = Field(default=None, description="1-based line number where the error ends")
    end_column: int | None = Field(default=None, description="1-based column number where the error ends")


class RuleVerifyResponse(BaseModel):
    """Response for rule verification."""

    valid: bool = Field(default=True, description="Whether the rule compiled successfully")
    params: list[str] = Field(default_factory=list, description="Parameters extracted from the rule")
    referenced_lists: list[str] = Field(
        default_factory=list, description="User list references extracted from the rule"
    )
    referenced_outcomes: list[str] = Field(
        default_factory=list, description="Outcome references extracted from the rule"
    )
    warnings: list[str] = Field(default_factory=list, description="Advisory warnings about referenced fields")
    errors: list[RuleVerifyError] = Field(default_factory=list, description="Structured validation failures")


class RuleAILineExplanation(BaseModel):
    """Explanation for a single generated rule line."""

    line_number: int = Field(..., ge=1, description="1-based line number in draft_logic")
    source: str = Field(..., description="Exact rule source line")
    explanation: str = Field(..., description="Human-readable explanation for the line")


class RuleAIDraftResponse(BaseModel):
    """Response for AI-assisted draft generation."""

    generation_id: str = Field(..., description="Identifier for this generated draft, used when applying it")
    draft_logic: str = Field(..., description="Generated ezrules draft logic")
    line_explanations: list[RuleAILineExplanation] = Field(
        default_factory=list,
        description="Line-by-line explanations for the generated draft",
    )
    validation: RuleVerifyResponse = Field(..., description="Validation result after generation and repair attempts")
    repair_attempted: bool = Field(default=False, description="Whether automatic repair was attempted")
    applyable: bool = Field(default=False, description="Whether the draft is valid enough to apply to the editor")
    provider: str = Field(..., description="Configured backend provider name")


class RuleAIDraftApplyResponse(BaseModel):
    """Response for explicit AI draft application tracking."""

    success: bool = Field(..., description="Whether the application event was recorded")
    message: str = Field(..., description="Human-readable result message")


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


class RuleReorderResponse(BaseModel):
    """Response for main-rule reorder operations."""

    success: bool
    message: str
