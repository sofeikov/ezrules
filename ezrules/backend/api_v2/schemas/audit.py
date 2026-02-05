"""
Pydantic schemas for audit trail API endpoints.

These schemas define the request/response format for the Audit Trail API.
The audit trail tracks changes to rules and rule engine configurations.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class ResourceType(str, Enum):
    """Types of resources that can be audited."""

    RULE = "rule"
    RULE_ENGINE_CONFIG = "rule_engine_config"


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class RuleHistoryEntry(BaseModel):
    """A single entry in rule history."""

    r_id: int = Field(..., description="Rule ID")
    rid: str = Field(..., description="Rule identifier")
    version: int = Field(..., description="Version number")
    logic: str = Field(..., description="Rule logic at this version")
    description: str = Field(..., description="Rule description at this version")
    changed: datetime | None = Field(default=None, description="When this version was created")

    model_config = {"from_attributes": True}


class RuleEngineConfigHistoryEntry(BaseModel):
    """A single entry in rule engine config history."""

    re_id: int = Field(..., description="Config ID")
    label: str = Field(..., description="Config label")
    version: int = Field(..., description="Version number")
    config: dict = Field(..., description="Configuration at this version")
    changed: datetime | None = Field(default=None, description="When this version was created")

    model_config = {"from_attributes": True}


class RuleAuditResponse(BaseModel):
    """Audit trail for a specific rule."""

    r_id: int = Field(..., description="Rule ID")
    rid: str = Field(..., description="Rule identifier")
    current_version: int = Field(..., description="Current version number")
    history: list[RuleHistoryEntry] = Field(default_factory=list, description="Version history")


class RulesAuditListResponse(BaseModel):
    """Paginated list of rule audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[RuleHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class ConfigAuditListResponse(BaseModel):
    """Paginated list of config audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[RuleEngineConfigHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class AuditSummaryResponse(BaseModel):
    """Summary of audit trail data."""

    total_rule_versions: int = Field(..., description="Total rule history entries")
    total_config_versions: int = Field(..., description="Total config history entries")
    rules_with_changes: int = Field(..., description="Number of rules with history")
    configs_with_changes: int = Field(..., description="Number of configs with history")
