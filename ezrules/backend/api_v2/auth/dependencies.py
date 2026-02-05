"""
FastAPI dependencies for authentication.

Dependencies are reusable functions that FastAPI "injects" into your route handlers.
Think of them as middleware that runs before your route code.

Example usage in a route:

    @router.get("/protected")
    def protected_route(user: User = Depends(get_current_user)):
        # 'user' is automatically populated by get_current_user
        # If the token is invalid, we never reach this code - FastAPI returns 401
        return {"message": f"Hello {user.email}"}

The magic is in `Depends()`. FastAPI sees it and:
1. Calls get_current_user() before your route
2. Passes the return value as the 'user' parameter
3. If get_current_user raises an HTTPException, the route is never called
"""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ezrules.backend.api_v2.auth.jwt import decode_token
from ezrules.models.backend_core import User
from ezrules.models.database import db_session

# =============================================================================
# OAuth2 SCHEME
# =============================================================================

# This tells FastAPI where to look for the token.
# OAuth2PasswordBearer means: "Look in the Authorization header for 'Bearer <token>'"
#
# The tokenUrl is used by Swagger UI's "Authorize" button.
# When you click it and enter credentials, Swagger POSTs to this URL.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/login")


# =============================================================================
# DATABASE SESSION DEPENDENCY
# =============================================================================


def get_db() -> Any:
    """
    Get a database session.

    This wraps the existing scoped_session from ezrules.
    In the future, this could be changed to use FastAPI's proper
    async session management, but for now we reuse the existing setup.

    Returns Any to satisfy type checker - the scoped_session works like a Session.
    """
    return db_session


# =============================================================================
# USER AUTHENTICATION DEPENDENCIES
# =============================================================================


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Any = Depends(get_db),
) -> User:
    """
    Validate the JWT token and return the corresponding User.

    This is the main authentication dependency. Use it like:

        @router.get("/me")
        def get_me(user: User = Depends(get_current_user)):
            return user

    How it works:
    1. FastAPI extracts the token from "Authorization: Bearer <token>" header
    2. We decode the token and verify it's valid (signature + not expired)
    3. We look up the user in the database
    4. We return the User object (or raise 401 if anything fails)

    Args:
        token: JWT token extracted from Authorization header (injected by oauth2_scheme)
        db: Database session (injected by get_db)

    Returns:
        The authenticated User object

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
    """
    # Define the exception we'll raise on any auth failure
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        # This header tells the client what auth scheme we expect
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode the token - this verifies signature and expiration
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    # Make sure it's an access token, not a refresh token
    # (Refresh tokens should only be accepted at /auth/refresh)
    if payload.token_type != "access":
        raise credentials_exception

    # Look up the user in the database
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    Get the current user and verify they're active.

    This is a stricter version of get_current_user that also checks
    the user's 'active' flag. Use this for most protected endpoints.

    A user might be inactive if:
    - An admin disabled their account
    - They were suspended for policy violations
    - Their trial period ended

    Args:
        user: The authenticated user (injected by get_current_user)

    Returns:
        The User object if active

    Raises:
        HTTPException 401: If user is not active
    """
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )
    return user
