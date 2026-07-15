import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ezrules.settings import app_settings

SECRET_ENCRYPTION_PREFIX = "fernet:v1:"


def encrypt_secret(value: str) -> str:
    """Encrypt a recoverable application secret with the configured app secret."""
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return SECRET_ENCRYPTION_PREFIX + token


def decrypt_secret(encrypted_value: str) -> str:
    """Decrypt a versioned application secret, rejecting plaintext and tampering."""
    if not encrypted_value.startswith(SECRET_ENCRYPTION_PREFIX):
        raise ValueError("Secret is not encrypted with a supported format")

    token = encrypted_value.removeprefix(SECRET_ENCRYPTION_PREFIX).encode("utf-8")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Secret could not be decrypted") from exc


def _fernet() -> Fernet:
    digest = hashlib.sha256(app_settings.APP_SECRET.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
