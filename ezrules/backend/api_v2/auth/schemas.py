"""
Pydantic schemas for authentication requests and responses.

Pydantic schemas serve two purposes:
1. Validation: Automatically check that incoming JSON has the right fields/types
2. Documentation: FastAPI uses these to generate OpenAPI docs

When you define a schema and use it in a route, FastAPI will:
- Parse the incoming JSON
- Validate it against the schema
- Return 422 Unprocessable Entity if validation fails
- Give you a nice Python object to work with
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr

# =============================================================================
# REQUEST SCHEMAS (what the client sends to us)
# =============================================================================


class LoginRequest(BaseModel):
    """
    Login request payload.

    Example JSON:
    {
        "email": "admin@example.com",
        "password": "secretpassword"
    }

    The EmailStr type automatically validates email format.
    If someone sends "not-an-email", FastAPI returns a 422 error.
    """

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """
    Refresh token request payload.

    Example JSON:
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
    }

    This is used when the access token expires and the client
    wants a new one without re-entering their password.
    """

    refresh_token: str


# =============================================================================
# RESPONSE SCHEMAS (what we send back to the client)
# =============================================================================


class TokenResponse(BaseModel):
    """
    Successful login/refresh response.

    Example response:
    {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "expires_in": 1800
    }

    The client will:
    1. Store both tokens (localStorage, memory, etc.)
    2. Send access_token in Authorization header: "Bearer eyJ..."
    3. When access_token expires, use refresh_token to get a new pair
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # Always "bearer" for JWT
    expires_in: int  # Seconds until access_token expires


class RoleResponse(BaseModel):
    """
    Role information for user response.

    Example:
    {
        "id": 1,
        "name": "admin",
        "description": "Full system administrator"
    }
    """

    id: int
    name: str
    description: str | None = None


class UserResponse(BaseModel):
    """
    User information response (for /auth/me endpoint).

    Example response:
    {
        "id": 1,
        "email": "admin@example.com",
        "active": true,
        "roles": [
            {"id": 1, "name": "admin", "description": "Full system administrator"}
        ],
        "last_login_at": "2024-01-15T10:30:00Z"
    }

    This is useful for:
    - Angular showing "Logged in as: admin@example.com"
    - Checking user's roles for UI decisions (show/hide admin buttons)
    """

    id: int
    email: str
    active: bool
    roles: list[RoleResponse]
    last_login_at: datetime | None = None

    class Config:
        # This tells Pydantic to read attributes from SQLAlchemy models
        # Without this, User.email wouldn't work - it would expect user["email"]
        from_attributes = True


class ErrorResponse(BaseModel):
    """
    Standard error response format.

    Example:
    {
        "detail": "Invalid email or password"
    }

    FastAPI uses this format by default for HTTP exceptions.
    We define it here for documentation purposes.
    """

    detail: str
