"""
Pydantic schemas for outcome-related API endpoints.

These schemas define the request/response format for the Outcomes API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from datetime import datetime

from pydantic import BaseModel, Field

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


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class OutcomeResponse(BaseModel):
    """Single outcome details returned from API."""

    ao_id: int = Field(..., description="Database primary key")
    outcome_name: str = Field(..., description="Outcome name (uppercase)")
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class OutcomeListItem(BaseModel):
    """Abbreviated outcome info for list endpoints."""

    ao_id: int
    outcome_name: str
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
