"""
FastAPI dependencies for authentication and authorization.

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

For permission checking, use require_permission():

    @router.get("/rules")
    def get_rules(
        user: User = Depends(get_current_active_user),
        _: None = Depends(require_permission(PermissionAction.VIEW_RULES))
    ):
        # Only reaches here if user is authenticated AND has VIEW_RULES permission
        return {"rules": [...]}
"""

from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ezrules.backend.api_v2.auth.jwt import decode_token
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, RoleActions, User
from ezrules.models.database import db_session

# =============================================================================
# OAuth2 SCHEME
# =============================================================================

# This tells FastAPI where to look for the token.
# OAuth2PasswordBearer means: "Look in the Authorization header for 'Bearer <token>'"
#
# The tokenUrl is used by Swagger UI's "Authorize" button.
# When you click it and enter credentials, Swagger POSTs to this URL.
# auto_error=False allows unauthenticated requests (for optional auth mode)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/login", auto_error=False)


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
    token: str | None = Depends(oauth2_scheme),
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

    Optional Auth Mode:
    If no token is provided AND no permissions exist in the database,
    return the first available user (for backward compatibility during migration).

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

    # If no token provided, check for optional auth mode
    if token is None:
        # Check if permissions have been initialized
        actions_exist = db.query(Action).first() is not None
        if not actions_exist:
            # No permissions configured - use first available user for backward compatibility
            first_user = db.query(User).filter(User.active.is_(True)).first()
            if first_user:
                return first_user
        raise credentials_exception

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

    This version supports optional auth mode - if no token is provided
    and no permissions are configured, it uses a default user.

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


# OAuth2 scheme that always requires a token (no optional auth)
oauth2_scheme_strict = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/login", auto_error=True)


def get_current_user_strict(
    token: str = Depends(oauth2_scheme_strict),
    db: Any = Depends(get_db),
) -> User:
    """
    Validate the JWT token and return the corresponding User.

    This is the strict version that ALWAYS requires a valid token.
    Use this for endpoints like /me where optional auth makes no sense.

    Args:
        token: JWT token extracted from Authorization header
        db: Database session

    Returns:
        The authenticated User object

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    if payload.token_type != "access":
        raise credentials_exception

    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user_strict(
    user: User = Depends(get_current_user_strict),
) -> User:
    """
    Get the current user and verify they're active (strict mode).

    Use this for endpoints that ALWAYS require authentication,
    like /me, /change-password, etc.

    Args:
        user: The authenticated user

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


# =============================================================================
# PERMISSION CHECKING DEPENDENCIES
# =============================================================================


def require_permission(
    action: PermissionAction,
    resource_id: int | None = None,
) -> Callable[..., None]:
    """
    Create a dependency that checks if the user has a specific permission.

    This is a "dependency factory" - it returns a dependency function.
    The returned function is what FastAPI actually calls.

    Usage:

        @router.get("/rules")
        def get_rules(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.VIEW_RULES))
        ):
            ...

        # With resource-specific permission:
        @router.delete("/rules/{rule_id}")
        def delete_rule(
            rule_id: int,
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_permission(PermissionAction.DELETE_RULE))
        ):
            ...

    How it works:
    1. require_permission(VIEW_RULES) is called at import time
    2. It returns the `check_permission` function
    3. When a request comes in, FastAPI calls check_permission()
    4. check_permission gets the current user and checks their permissions
    5. If permission denied, raises 403. Otherwise, returns None.

    Args:
        action: The permission action to check (from PermissionAction enum)
        resource_id: Optional specific resource ID to check permission for

    Returns:
        A dependency function that checks the permission
    """

    def check_permission(
        user: User = Depends(get_current_active_user),
        db: Any = Depends(get_db),
    ) -> None:
        """
        The actual permission checking logic.

        This function is called by FastAPI for each request to a protected route.
        """
        # Check if permissions have been initialized in the database
        # If no actions exist, we're in backward-compatibility mode - allow all
        actions_exist = db.query(Action).first() is not None
        if not actions_exist:
            return None

        # Convert enum to string for database lookup
        action_str = action.value if isinstance(action, PermissionAction) else action

        # Find the action in the database
        db_action = db.query(Action).filter_by(name=action_str).first()
        if not db_action:
            # Action doesn't exist in DB - this shouldn't happen if DB is properly initialized
            # Fail secure: deny access
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        # Check if any of the user's roles have this permission
        for role in user.roles:
            role_action = (
                db.query(RoleActions)
                .filter_by(role_id=role.id, action_id=db_action.id)
                .filter((RoleActions.resource_id == resource_id) | (RoleActions.resource_id.is_(None)))
                .first()
            )
            if role_action:
                # Permission granted!
                return None

        # No matching permission found
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    return check_permission


def require_any_permission(*actions: PermissionAction) -> Callable[..., None]:
    """
    Create a dependency that checks if the user has ANY of the specified permissions.

    Useful when multiple permissions could grant access to the same resource.

    Usage:

        @router.get("/dashboard")
        def get_dashboard(
            user: User = Depends(get_current_active_user),
            _: None = Depends(require_any_permission(
                PermissionAction.VIEW_RULES,
                PermissionAction.VIEW_OUTCOMES
            ))
        ):
            # User needs VIEW_RULES OR VIEW_OUTCOMES to access
            ...

    Args:
        *actions: Variable number of PermissionAction values to check

    Returns:
        A dependency function that checks if user has any of the permissions
    """

    def check_any_permission(
        user: User = Depends(get_current_active_user),
        db: Any = Depends(get_db),
    ) -> None:
        """Check if user has any of the specified permissions."""
        # Check if permissions have been initialized
        actions_exist = db.query(Action).first() is not None
        if not actions_exist:
            return None

        # Check each permission
        for action in actions:
            action_str = action.value if isinstance(action, PermissionAction) else action
            db_action = db.query(Action).filter_by(name=action_str).first()

            if db_action:
                for role in user.roles:
                    role_action = (
                        db.query(RoleActions)
                        .filter_by(role_id=role.id, action_id=db_action.id)
                        .filter(RoleActions.resource_id.is_(None))
                        .first()
                    )
                    if role_action:
                        return None

        # No matching permission found
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    return check_any_permission
