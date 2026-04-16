"""
Pydantic schemas for outcome-related API endpoints.

These schemas define the request/response format for the Outcomes API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

OUTCOME_NAME_PATTERN = r"^[A-Z_][A-Z0-9_]*$"

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class OutcomeCreate(BaseModel):
    """Schema for creating a new outcome."""

    outcome_name: str = Field(
        ...,
        min_length=1,
        description="Name of the outcome (will be converted to uppercase)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_name": "REVIEW",
            }
        }
    }

    @field_validator("outcome_name", mode="before")
    @classmethod
    def normalize_outcome_name(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if not normalized:
            raise ValueError("Outcome name cannot be empty")
        return normalized

    @field_validator("outcome_name")
    @classmethod
    def validate_outcome_name(cls, value: str) -> str:
        if not re.fullmatch(OUTCOME_NAME_PATTERN, value):
            raise ValueError("Outcome name must use uppercase letters, numbers, and underscores only")
        return value


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class OutcomeResponse(BaseModel):
    """Single outcome details returned from API."""

    ao_id: int = Field(..., description="Database primary key")
    outcome_name: str = Field(..., description="Outcome name (uppercase)")
    severity_rank: int = Field(..., ge=1, description="Configured severity rank; 1 is the highest severity")
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class OutcomeListItem(BaseModel):
    """Abbreviated outcome info for list endpoints."""

    ao_id: int
    outcome_name: str
    severity_rank: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class OutcomesListResponse(BaseModel):
    """Response for GET /outcomes endpoint."""

    outcomes: list[OutcomeListItem]


class OutcomeMutationResponse(BaseModel):
    """Response for create/delete operations."""

    success: bool
    message: str
    outcome: OutcomeResponse | None = None
    error: str | None = None
