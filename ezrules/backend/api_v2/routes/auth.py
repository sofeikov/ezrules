"""
Authentication routes for the API v2.

Endpoints:
- POST /api/v2/auth/login  - Exchange email/password for tokens
- POST /api/v2/auth/refresh - Exchange refresh token for new access token
- GET  /api/v2/auth/me     - Get current user info (test endpoint)
"""

from datetime import UTC, datetime
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ezrules.backend.api_v2.auth.dependencies import get_current_active_user_strict, get_db
from ezrules.backend.api_v2.auth.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ezrules.backend.api_v2.auth.schemas import (
    RefreshRequest,
    RoleResponse,
    TokenResponse,
    UserResponse,
)
from ezrules.models.backend_core import User

# Create a router with a prefix and tag for organization
# All routes here will be under /api/v2/auth/...
router = APIRouter(prefix="/api/v2/auth", tags=["Authentication"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    This works with passwords created by both:
    - CLI: bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    - Flask-Security: hash_password(password)

    Both use bcrypt under the hood, so the same verification works.

    Args:
        plain_password: The password the user typed in
        hashed_password: The hash stored in the database

    Returns:
        True if password matches, False otherwise
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def authenticate_user(db: Any, email: str, password: str) -> User | None:
    """
    Find a user by email and verify their password.

    Args:
        db: Database session
        email: Email address to look up
        password: Plain text password to verify

    Returns:
        User object if authentication succeeds, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user


# =============================================================================
# LOGIN ENDPOINT
# =============================================================================


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"description": "Invalid email or password"},
    },
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Any = Depends(get_db),
):
    """
    Authenticate user and return JWT tokens.

    This endpoint accepts credentials and returns an access token + refresh token.

    **How to use:**

    1. Send a POST request with form data (not JSON!):
       - username: The user's email address
       - password: The user's password

    2. On success, you get back:
       - access_token: Use this in Authorization header for API calls
       - refresh_token: Use this to get new access tokens
       - expires_in: Seconds until access_token expires

    3. For subsequent API calls, include the header:
       `Authorization: Bearer <access_token>`

    **Why form data instead of JSON?**

    OAuth2 spec requires form data for the token endpoint. This also makes
    the Swagger UI "Authorize" button work out of the box.
    The field is called "username" (OAuth2 standard) but we expect an email.
    """
    # Authenticate the user
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user's role names for the token payload
    role_names = [role.name for role in user.roles]

    # Create tokens
    # Cast to int/str for type checker - SQLAlchemy columns have complex types
    access_token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=role_names,
    )
    refresh_token = create_refresh_token(user_id=int(user.id))

    # Update login tracking (optional but nice to have)
    user.last_login_at = user.current_login_at
    user.current_login_at = datetime.now(UTC)
    if user.login_count is None:
        user.login_count = 1
    else:
        user.login_count += 1
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
    )


# =============================================================================
# REFRESH TOKEN ENDPOINT
# =============================================================================


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
)
def refresh_token(
    request: RefreshRequest,
    db: Any = Depends(get_db),
):
    """
    Exchange a refresh token for a new access token.

    **When to use this:**

    When your access token expires (after 30 minutes), you have two choices:
    1. Make the user log in again (bad UX)
    2. Use the refresh token to get a new access token (good UX)

    **How it works:**

    1. Send your refresh_token in the request body
    2. If valid, you get back a fresh pair of tokens
    3. The old refresh token is still valid until it expires

    **Security note:**

    This endpoint also checks that the user still exists and is active.
    If an admin deactivates a user, their refresh tokens stop working.
    """
    # Decode the refresh token
    payload = decode_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify it's a refresh token, not an access token
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Look up the user - they might have been deleted/deactivated since login
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    role_names = [role.name for role in user.roles]
    access_token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=role_names,
    )
    new_refresh_token = create_refresh_token(user_id=int(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# =============================================================================
# ME ENDPOINT (for testing/debugging)
# =============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated or token expired"},
    },
)
def get_current_user_info(
    user: User = Depends(get_current_active_user_strict),
):
    """
    Get information about the currently authenticated user.

    This is a simple endpoint to:
    1. Test that authentication is working
    2. Get the current user's info for display in the UI

    **How to use:**

    Include your access token in the Authorization header:
    `Authorization: Bearer <access_token>`

    **What you get back:**

    - id: User's database ID
    - email: User's email
    - active: Whether the account is enabled
    - roles: List of roles with names and descriptions
    - last_login_at: When the user last logged in
    """
    # Cast last_login_at - it's either a datetime or None
    last_login = user.last_login_at if user.last_login_at is not None else None
    return UserResponse(
        id=int(user.id),
        email=str(user.email),
        active=bool(user.active),
        roles=[RoleResponse(id=int(role.id), name=str(role.name), description=role.description) for role in user.roles],
        last_login_at=last_login,  # type: ignore[arg-type]
    )
