"""
Pydantic schemas for user management API endpoints.

These schemas define the request/response format for the Users API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=6, description="User's password (min 6 characters)")
    role_ids: list[int] | None = Field(default=None, description="Optional list of role IDs to assign")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newuser@example.com",
                "password": "securepassword123",
                "role_ids": [1, 2],
            }
        }
    }


class UserUpdate(BaseModel):
    """Schema for updating an existing user.

    All fields are optional - only provided fields will be updated.
    """

    email: EmailStr | None = Field(default=None, description="New email address")
    password: str | None = Field(default=None, min_length=6, description="New password (min 6 characters)")
    active: bool | None = Field(default=None, description="Whether the user is active")


class AssignRoleRequest(BaseModel):
    """Schema for assigning a role to a user."""

    role_id: int = Field(..., description="ID of the role to assign")

    model_config = {
        "json_schema_extra": {
            "example": {
                "role_id": 1,
            }
        }
    }


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class RoleResponse(BaseModel):
    """Role details returned from API."""

    id: int = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")
    description: str | None = Field(default=None, description="Role description")

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Full user details returned from API."""

    id: int = Field(..., description="User ID")
    email: str = Field(..., description="User's email address")
    active: bool = Field(..., description="Whether the user is active")
    roles: list[RoleResponse] = Field(default_factory=list, description="Assigned roles")
    last_login_at: datetime | None = Field(default=None, description="Last login timestamp")
    current_login_at: datetime | None = Field(default=None, description="Current login timestamp")

    model_config = {"from_attributes": True}


class UserListItem(BaseModel):
    """Abbreviated user info for list endpoints."""

    id: int
    email: str
    active: bool
    roles: list[RoleResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UsersListResponse(BaseModel):
    """Response for GET /users endpoint."""

    users: list[UserListItem]


class UserMutationResponse(BaseModel):
    """Response for create/update/delete operations."""

    success: bool
    message: str
    user: UserResponse | None = None
    error: str | None = None


class RoleAssignmentResponse(BaseModel):
    """Response for role assignment operations."""

    success: bool
    message: str
    user: UserResponse | None = None
    error: str | None = None
