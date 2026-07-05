from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CaseEventResponse(BaseModel):
    id: int
    case_id: int
    event_type: str
    actor_user_id: int | None = None
    source_ed_id: int | None = None
    external_event_id: str
    occurred_at: datetime
    details: dict
    created_at: datetime


class CaseResponse(BaseModel):
    id: int
    transaction_id: str
    current_event_version_id: int
    current_evaluation_decision_id: int
    opened_by_evaluation_decision_id: int
    previous_evaluation_decision_id: int | None = None
    resolved_outcome: str | None = None
    previous_resolved_outcome: str | None = None
    status: str
    decision_state: str
    priority: int
    assigned_to_user_id: int | None = None
    resolved_by_user_id: int | None = None
    resolution_note: str | None = None
    resolution_label_id: int | None = None
    reopened_from_case_id: int | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    total: int


class CaseDetailResponse(BaseModel):
    case: CaseResponse
    events: list[CaseEventResponse]


class CaseUpdateRequest(BaseModel):
    assigned_to_user_id: int | None = None


class CaseResolveRequest(BaseModel):
    resolution_note: str = Field(..., min_length=1, max_length=5000)
    resolution_label_id: int | None = None
    expected_current_ed_id: int | None = None

    @field_validator("resolution_note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("resolution_note cannot be empty")
        return stripped


class CaseMutationResponse(BaseModel):
    success: bool
    message: str
    case: CaseResponse


class IntegrationEventResponse(BaseModel):
    id: int
    external_event_id: str
    source_type: str
    source_id: int
    event_type: str
    event_version: int
    occurred_at: datetime
    payload: dict
    created_at: datetime


class IntegrationEventsResponse(BaseModel):
    events: list[IntegrationEventResponse]
    next_cursor: int | None = None


class IntegrationSubscriptionResponse(BaseModel):
    id: int
    name: str
    destination_type: str
    config: dict
    event_types: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class IntegrationSubscriptionsResponse(BaseModel):
    subscriptions: list[IntegrationSubscriptionResponse]


class IntegrationSubscriptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    destination_type: str = Field(..., min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)
    event_types: list[str] = Field(default_factory=list)
    enabled: bool = True


class IntegrationSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    destination_type: str | None = Field(default=None, min_length=1, max_length=64)
    config: dict | None = None
    event_types: list[str] | None = None
    enabled: bool | None = None


class IntegrationSubscriptionMutationResponse(BaseModel):
    success: bool
    message: str
    subscription: IntegrationSubscriptionResponse
