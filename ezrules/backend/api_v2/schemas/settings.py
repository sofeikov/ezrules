"""Pydantic schemas for runtime settings endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class RuntimeSettingsResponse(BaseModel):
    """Current runtime settings used by configurable backend features."""

    rule_quality_lookback_days: int = Field(..., ge=1, description="Default lookback (days) for rule-quality analytics")
    default_rule_quality_lookback_days: int = Field(
        ..., ge=1, description="Fallback env-based default lookback in days"
    )


class RuntimeSettingsUpdateRequest(BaseModel):
    """Request payload for runtime settings updates."""

    rule_quality_lookback_days: int = Field(..., ge=1, le=3650)


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
