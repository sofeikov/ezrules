"""Pydantic schemas for runtime settings endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class RuntimeSettingsResponse(BaseModel):
    """Current runtime settings used by configurable backend features."""

    auto_promote_active_rule_updates: bool = Field(
        ..., description="Whether edits to active rules are auto-promoted in place"
    )
    default_auto_promote_active_rule_updates: bool = Field(
        ..., description="Fallback default for active-rule auto-promotion"
    )
    main_rule_execution_mode: str = Field(..., description="How main rules are evaluated: all matches or first match")
    default_main_rule_execution_mode: str = Field(..., description="Fallback execution mode for main rules")
    rule_quality_lookback_days: int = Field(..., ge=1, description="Default lookback (days) for rule-quality analytics")
    default_rule_quality_lookback_days: int = Field(
        ..., ge=1, description="Fallback env-based default lookback in days"
    )
    neutral_outcome: str = Field(..., description="Configured neutral outcome reused by allowlist and future policies")
    default_neutral_outcome: str = Field(..., description="Fallback default neutral outcome")
    invalid_allowlist_rules: list["InvalidAllowlistRule"] = Field(
        default_factory=list,
        description="Existing allowlist rules that do not comply with the configured neutral outcome",
    )


class RuntimeSettingsUpdateRequest(BaseModel):
    """Request payload for runtime settings updates."""

    auto_promote_active_rule_updates: bool | None = Field(default=None)
    main_rule_execution_mode: str | None = Field(default=None, min_length=1, max_length=64)
    rule_quality_lookback_days: int | None = Field(default=None, ge=1, le=3650)
    neutral_outcome: str | None = Field(default=None, min_length=1, max_length=255)


class AIAuthoringSettingsResponse(BaseModel):
    """Current AI authoring settings managed through the Settings page."""

    provider: str = Field(..., description="Configured AI provider")
    supported_providers: list[str] = Field(default_factory=list, description="Providers currently supported by the app")
    enabled: bool = Field(..., description="Whether AI rule authoring is enabled")
    model: str = Field(..., description="Configured model name")
    api_key_configured: bool = Field(..., description="Whether an API key is currently stored")


class AIAuthoringSettingsUpdateRequest(BaseModel):
    """Update request for AI authoring settings."""

    provider: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = Field(default=None)
    model: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=2048)
    clear_api_key: bool | None = Field(default=None)


class InvalidAllowlistRule(BaseModel):
    """Existing allowlist rule that no longer matches the configured neutral outcome."""

    r_id: int = Field(..., description="Rule ID")
    rid: str = Field(..., description="Rule external identifier")
    description: str = Field(..., description="Rule description")
    error: str = Field(..., description="Validation error explaining the mismatch")


class OutcomeHierarchyItem(BaseModel):
    """Allowed outcome with its configured severity order."""

    ao_id: int = Field(..., description="Outcome ID")
    outcome_name: str = Field(..., description="Outcome name")
    severity_rank: int = Field(..., ge=1, description="1-based severity rank; lower values are more severe")


class OutcomeHierarchyResponse(BaseModel):
    """Ordered list of outcomes used to resolve conflicting rule hits."""

    outcomes: list[OutcomeHierarchyItem] = Field(default_factory=list)


class OutcomeHierarchyUpdateRequest(BaseModel):
    """Replace the full outcome hierarchy ordering."""

    ordered_ao_ids: list[int] = Field(
        default_factory=list, description="Outcome IDs ordered from highest to lowest severity"
    )


class RuleQualityPairResponse(BaseModel):
    """Configured curated pair used by rule-quality analytics."""

    rqp_id: int = Field(..., description="Rule quality pair ID")
    outcome: str = Field(..., description="Configured rule outcome name")
    label: str = Field(..., description="Configured transaction label name")
    active: bool = Field(..., description="Whether this pair is active for reporting")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: str | None = Field(default=None, description="Email of creator")


class RuleQualityPairsListResponse(BaseModel):
    """List response for curated rule-quality pairs."""

    pairs: list[RuleQualityPairResponse] = Field(default_factory=list)


class RuleQualityPairOptionsResponse(BaseModel):
    """Available option catalogs for curated pair creation."""

    outcomes: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class RuleQualityPairCreateRequest(BaseModel):
    """Create request for a curated rule-quality pair."""

    outcome: str = Field(..., min_length=1, max_length=255)
    label: str = Field(..., min_length=1, max_length=255)


class RuleQualityPairUpdateRequest(BaseModel):
    """Update request for a curated rule-quality pair."""

    active: bool = Field(..., description="Enable or disable this pair")
