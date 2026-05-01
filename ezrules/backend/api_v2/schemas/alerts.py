from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AlertIncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    outcome: str = Field(..., min_length=1, max_length=255)
    threshold: int = Field(..., ge=1)
    window_seconds: int = Field(..., ge=60)
    cooldown_seconds: int = Field(default=1800, ge=0)
    enabled: bool = True

    @field_validator("name", "outcome")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return stripped


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    outcome: str | None = Field(default=None, min_length=1, max_length=255)
    threshold: int | None = Field(default=None, ge=1)
    window_seconds: int | None = Field(default=None, ge=60)
    cooldown_seconds: int | None = Field(default=None, ge=0)
    enabled: bool | None = None

    @field_validator("name", "outcome")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return stripped


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    outcome: str
    threshold: int
    window_seconds: int
    cooldown_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AlertRulesResponse(BaseModel):
    rules: list[AlertRuleResponse]


class AlertIncidentResponse(BaseModel):
    id: int
    alert_rule_id: int
    outcome: str
    observed_count: int
    threshold: int
    window_start: datetime
    window_end: datetime
    status: AlertIncidentStatus
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class AlertIncidentsResponse(BaseModel):
    incidents: list[AlertIncidentResponse]


class AlertMutationResponse(BaseModel):
    success: bool
    message: str
    rule: AlertRuleResponse | None = None
    incident: AlertIncidentResponse | None = None


class NotificationResponse(BaseModel):
    id: int
    severity: str
    title: str
    body: str
    action_url: str | None = None
    source_type: str
    source_id: int
    created_at: datetime
    read_at: datetime | None = None


class NotificationsResponse(BaseModel):
    notifications: list[NotificationResponse]


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int
