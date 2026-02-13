"""
Pydantic schemas for audit trail API endpoints.

These schemas define the request/response format for the Audit Trail API.
The audit trail tracks changes to rules and rule engine configurations.
"""

from datetime import datetime
from enum import Enum
from typing import Any

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
    changed_by: str | None = Field(default=None, description="Who made this change")

    model_config = {"from_attributes": True}


class RuleEngineConfigHistoryEntry(BaseModel):
    """A single entry in rule engine config history."""

    re_id: int = Field(..., description="Config ID")
    label: str = Field(..., description="Config label")
    version: int = Field(..., description="Version number")
    config: Any = Field(..., description="Configuration at this version")
    changed: datetime | None = Field(default=None, description="When this version was created")
    changed_by: str | None = Field(default=None, description="Who made this change")

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


class UserListHistoryEntry(BaseModel):
    """A single entry in user list history."""

    id: int = Field(..., description="History entry ID")
    ul_id: int = Field(..., description="User list ID")
    list_name: str = Field(..., description="List name at the time of the action")
    action: str = Field(
        ..., description="Action type (created, renamed, deleted, entry_added, entry_removed, entries_bulk_added)"
    )
    details: str | None = Field(default=None, description="Additional details about the action")
    changed: datetime | None = Field(default=None, description="When this action occurred")
    changed_by: str | None = Field(default=None, description="Who performed this action")

    model_config = {"from_attributes": True}


class UserListAuditListResponse(BaseModel):
    """Paginated list of user list audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[UserListHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class OutcomeHistoryEntry(BaseModel):
    """A single entry in outcome history."""

    id: int = Field(..., description="History entry ID")
    ao_id: int = Field(..., description="Outcome ID")
    outcome_name: str = Field(..., description="Outcome name")
    action: str = Field(..., description="Action type (created, deleted)")
    changed: datetime | None = Field(default=None, description="When this action occurred")
    changed_by: str | None = Field(default=None, description="Who performed this action")

    model_config = {"from_attributes": True}


class OutcomeAuditListResponse(BaseModel):
    """Paginated list of outcome audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[OutcomeHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class LabelHistoryEntry(BaseModel):
    """A single entry in label history."""

    id: int = Field(..., description="History entry ID")
    el_id: int = Field(..., description="Label ID")
    label: str = Field(..., description="Label name")
    action: str = Field(..., description="Action type (created, deleted)")
    changed: datetime | None = Field(default=None, description="When this action occurred")
    changed_by: str | None = Field(default=None, description="Who performed this action")

    model_config = {"from_attributes": True}


class LabelAuditListResponse(BaseModel):
    """Paginated list of label audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[LabelHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class UserAccountHistoryEntry(BaseModel):
    """A single entry in user account history."""

    id: int = Field(..., description="History entry ID")
    user_id: int = Field(..., description="User ID")
    user_email: str = Field(..., description="User email at the time of the action")
    action: str = Field(
        ...,
        description="Action type (created, updated, deleted, activated, deactivated, role_assigned, role_removed)",
    )
    details: str | None = Field(default=None, description="Additional details about the action")
    changed: datetime | None = Field(default=None, description="When this action occurred")
    changed_by: str | None = Field(default=None, description="Who performed this action")

    model_config = {"from_attributes": True}


class UserAccountAuditListResponse(BaseModel):
    """Paginated list of user account audit entries."""

    total: int = Field(..., description="Total number of history entries")
    items: list[UserAccountHistoryEntry] = Field(default_factory=list)
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")


class AuditSummaryResponse(BaseModel):
    """Summary of audit trail data."""

    total_rule_versions: int = Field(..., description="Total rule history entries")
    total_config_versions: int = Field(..., description="Total config history entries")
    rules_with_changes: int = Field(..., description="Number of rules with history")
    configs_with_changes: int = Field(..., description="Number of configs with history")
    total_user_list_actions: int = Field(default=0, description="Total user list history entries")
    total_outcome_actions: int = Field(default=0, description="Total outcome history entries")
    total_label_actions: int = Field(default=0, description="Total label history entries")
    total_user_account_actions: int = Field(default=0, description="Total user account history entries")
