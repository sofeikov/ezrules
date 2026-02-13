"""
JWT token creation and validation utilities.

This module handles:
1. Creating access tokens (short-lived, used for API requests)
2. Creating refresh tokens (long-lived, used only to get new access tokens)
3. Decoding and validating tokens
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from ezrules.settings import app_settings

# =============================================================================
# CONFIGURATION
# =============================================================================

# We use the existing APP_SECRET as our JWT signing key.
# This is the secret that makes forgery impossible - keep it safe!
SECRET_KEY = app_settings.APP_SECRET

# Algorithm used for signing. HS256 = HMAC with SHA-256.
# This is symmetric encryption - same key signs and verifies.
ALGORITHM = "HS256"

# Token lifetimes
# Access tokens are short-lived because they're sent with every request.
# If one gets stolen, the damage is limited to this time window.
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Refresh tokens live longer. They're only sent to one endpoint (/auth/refresh)
# and are used to get new access tokens without re-entering password.
REFRESH_TOKEN_EXPIRE_DAYS = 7


# =============================================================================
# TOKEN CREATION
# =============================================================================


def create_access_token(user_id: int, email: str, roles: list[str]) -> str:
    """
    Create a short-lived access token for API authentication.

    The token contains:
    - sub (subject): The user's ID - this is the standard JWT claim for "who is this"
    - email: For convenience, so we don't always need to hit the DB
    - roles: User's role names, for quick permission checks
    - type: "access" - distinguishes from refresh tokens
    - iat (issued at): When the token was created
    - exp (expiration): When the token becomes invalid

    Args:
        user_id: The user's database ID
        email: The user's email address
        roles: List of role names the user has

    Returns:
        A signed JWT string like "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJz..."
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),  # JWT standard: subject should be a string
        "email": email,
        "roles": roles,
        "type": "access",
        "iat": now,
        "exp": expire,
    }

    # jwt.encode() does three things:
    # 1. Creates the header ({"alg": "HS256", "typ": "JWT"})
    # 2. Base64-encodes the payload
    # 3. Signs header.payload with SECRET_KEY and appends the signature
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """
    Create a long-lived refresh token.

    Refresh tokens are simpler - they only contain the user ID.
    They're used solely to get new access tokens, not to access resources.

    Why have refresh tokens at all?
    - Access tokens are sent with every request, so they're more exposed
    - If an access token is stolen, attacker has 30 min of access
    - Refresh tokens are only sent to /auth/refresh endpoint
    - If user logs out or is deactivated, we can reject the refresh

    Args:
        user_id: The user's database ID

    Returns:
        A signed JWT string
    """
    now = datetime.now(UTC)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# =============================================================================
# TOKEN DECODING / VALIDATION
# =============================================================================


class TokenPayload:
    """
    Structured representation of a decoded JWT payload.

    After decoding, we convert the raw dict to this class for type safety.
    """

    def __init__(self, user_id: int, email: str | None, roles: list[str], token_type: str):
        self.user_id = user_id
        self.email = email
        self.roles = roles
        self.token_type = token_type


def decode_token(token: str) -> TokenPayload | None:
    """
    Decode and validate a JWT token.

    This function:
    1. Verifies the signature (proves token wasn't tampered with)
    2. Checks expiration (rejects expired tokens)
    3. Extracts the payload data

    Args:
        token: The JWT string from the Authorization header

    Returns:
        TokenPayload if valid, None if invalid/expired

    Note:
        We return None instead of raising exceptions to make error handling
        simpler in the calling code. The caller just checks "if payload is None".
    """
    try:
        # jwt.decode() does:
        # 1. Splits token into header.payload.signature
        # 2. Recomputes signature using SECRET_KEY
        # 3. Compares computed vs received signature (rejects if different)
        # 4. Checks 'exp' claim against current time (rejects if expired)
        # 5. Returns the payload as a dict
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Extract user_id from 'sub' claim
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None

        return TokenPayload(
            user_id=int(user_id_str),
            email=payload.get("email"),
            roles=payload.get("roles", []),
            token_type=payload.get("type", "access"),
        )

    except JWTError:
        # This catches:
        # - Invalid signature (someone tampered with the token)
        # - Expired token (exp claim is in the past)
        # - Malformed token (not valid base64, wrong structure, etc.)
        return None
