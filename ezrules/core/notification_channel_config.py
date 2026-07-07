import base64
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from ezrules.settings import SETTINGS_ENV_FILE, app_settings

CONFIG_ENCRYPTION_PREFIX = "fernet:v1:"
REDACTED_VALUE = "[redacted]"
ALEMBIC_PLACEHOLDER_APP_SECRET = "alembic-placeholder-secret"


@dataclass(frozen=True, slots=True)
class NotificationChannelConfigSchema:
    required_fields: frozenset[str]
    optional_fields: frozenset[str]
    secret_fields: frozenset[str]

    @property
    def allowed_fields(self) -> frozenset[str]:
        return self.required_fields | self.optional_fields


CHANNEL_CONFIG_SCHEMAS: dict[str, NotificationChannelConfigSchema] = {
    "in_app": NotificationChannelConfigSchema(
        required_fields=frozenset(),
        optional_fields=frozenset(),
        secret_fields=frozenset(),
    ),
    "email": NotificationChannelConfigSchema(
        required_fields=frozenset({"to"}),
        optional_fields=frozenset({"from_email", "reply_to", "smtp_host", "smtp_port", "smtp_user", "smtp_password"}),
        secret_fields=frozenset({"smtp_password"}),
    ),
    "pagerduty": NotificationChannelConfigSchema(
        required_fields=frozenset({"routing_key"}),
        optional_fields=frozenset(),
        secret_fields=frozenset({"routing_key"}),
    ),
    "slack": NotificationChannelConfigSchema(
        required_fields=frozenset({"webhook_url"}),
        optional_fields=frozenset({"channel", "username", "icon_emoji", "signing_secret"}),
        secret_fields=frozenset({"webhook_url", "signing_secret"}),
    ),
    "webhook": NotificationChannelConfigSchema(
        required_fields=frozenset({"url"}),
        optional_fields=frozenset({"method", "headers", "signing_secret", "timeout_seconds"}),
        secret_fields=frozenset({"url", "headers.authorization", "headers.x-api-key", "signing_secret"}),
    ),
}

_SECRET_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/\-]+=*", re.IGNORECASE), rf"\1{REDACTED_VALUE}"),
    (re.compile(r"([?&](?:api_?key|code|secret|sig|signature|token)=)[^&\s]+", re.IGNORECASE), rf"\1{REDACTED_VALUE}"),
)


def normalize_notification_channel_type(channel_type: str) -> str:
    normalized = channel_type.strip().lower()
    if normalized not in CHANNEL_CONFIG_SCHEMAS:
        allowed = ", ".join(sorted(CHANNEL_CONFIG_SCHEMAS))
        raise ValueError(f"Unsupported notification channel type '{channel_type}'. Allowed types: {allowed}")
    return normalized


def validate_notification_channel_config(channel_type: str, config: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized_type = normalize_notification_channel_type(channel_type)
    if config is None:
        candidate: dict[str, Any] = {}
    elif isinstance(config, Mapping):
        candidate = dict(config)
    else:
        raise ValueError("Notification channel config must be a JSON object")

    schema = CHANNEL_CONFIG_SCHEMAS[normalized_type]
    unknown_fields = sorted(set(candidate) - schema.allowed_fields)
    if unknown_fields:
        raise ValueError(f"Unsupported config field(s) for {normalized_type}: {', '.join(unknown_fields)}")

    missing_fields = sorted(field for field in schema.required_fields if _is_empty_value(candidate.get(field)))
    if missing_fields:
        raise ValueError(f"Missing required config field(s) for {normalized_type}: {', '.join(missing_fields)}")

    _validate_field_shapes(normalized_type, candidate)
    return candidate


def encrypt_notification_channel_config(channel_type: str, config: Mapping[str, Any] | None) -> str:
    validated_config = validate_notification_channel_config(channel_type, config)
    return encrypt_notification_channel_config_unvalidated(validated_config)


def encrypt_notification_channel_config_unvalidated(config: Any) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return CONFIG_ENCRYPTION_PREFIX + _fernet().encrypt(payload).decode("utf-8")


def decrypt_notification_channel_config(channel_type: str, encrypted_config: str | None) -> dict[str, Any]:
    decoded = decrypt_notification_channel_config_unvalidated(encrypted_config)
    try:
        return validate_notification_channel_config(channel_type, decoded)
    except ValueError:
        if isinstance(decoded, Mapping):
            return dict(decoded)
        return {"legacy_value": decoded}


def decrypt_notification_channel_config_unvalidated(encrypted_config: str | None) -> Any:
    if not encrypted_config:
        return {}
    if not encrypted_config.startswith(CONFIG_ENCRYPTION_PREFIX):
        raise ValueError("Notification channel config is not encrypted with a supported format")

    token = encrypted_config.removeprefix(CONFIG_ENCRYPTION_PREFIX).encode("utf-8")
    try:
        payload = _fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Notification channel config could not be decrypted") from exc

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Notification channel config decrypted to invalid JSON") from exc
    return decoded


def redact_notification_channel_config(channel_type: str, config: Mapping[str, Any] | None) -> dict[str, Any]:
    validated_config = validate_notification_channel_config(channel_type, config)
    schema = CHANNEL_CONFIG_SCHEMAS[normalize_notification_channel_type(channel_type)]
    return {key: _redact_config_value((key,), value, schema.secret_fields) for key, value in validated_config.items()}


def redact_notification_channel_error(
    channel_type: str,
    config: Mapping[str, Any] | None,
    error_message: str | None,
) -> str | None:
    if error_message is None:
        return None

    redacted_message = error_message
    for secret_value in _iter_secret_values_for_error(channel_type, config):
        if secret_value:
            redacted_message = redacted_message.replace(secret_value, REDACTED_VALUE)
    for pattern, replacement in _SECRET_TEXT_PATTERNS:
        redacted_message = pattern.sub(replacement, redacted_message)
    return redacted_message


def _fernet() -> Fernet:
    digest = hashlib.sha256(_notification_config_app_secret().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _notification_config_app_secret() -> str:
    env_secret = os.getenv("EZRULES_APP_SECRET")
    if env_secret and env_secret != ALEMBIC_PLACEHOLDER_APP_SECRET:
        return env_secret

    env_file_secret = _read_app_secret_from_settings_env()
    if env_file_secret:
        return env_file_secret

    if app_settings.APP_SECRET and app_settings.APP_SECRET != ALEMBIC_PLACEHOLDER_APP_SECRET:
        return app_settings.APP_SECRET

    raise ValueError("Notification channel config encryption requires a non-placeholder EZRULES_APP_SECRET")


def _read_app_secret_from_settings_env() -> str | None:
    env_file = Path(SETTINGS_ENV_FILE)
    if not env_file.exists():
        return None

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "EZRULES_APP_SECRET":
            continue
        return value.strip().strip('"').strip("'")
    return None


def _is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _validate_field_shapes(channel_type: str, config: Mapping[str, Any]) -> None:
    if channel_type == "in_app" and config:
        raise ValueError("in_app notification channel config must be empty")

    for field in ("url", "webhook_url"):
        if field in config:
            _validate_http_url(field, config[field])

    if "method" in config:
        method = config["method"]
        if method not in {"POST", "PUT", "PATCH"}:
            raise ValueError("webhook method must be one of POST, PUT, PATCH")

    if "headers" in config:
        headers = config["headers"]
        if not isinstance(headers, Mapping):
            raise ValueError("webhook headers must be a JSON object")
        for key, value in headers.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("webhook header names must be non-empty strings")
            if not isinstance(value, str):
                raise ValueError("webhook header values must be strings")

    if "timeout_seconds" in config:
        timeout_seconds = config["timeout_seconds"]
        if not isinstance(timeout_seconds, int) or timeout_seconds < 1 or timeout_seconds > 60:
            raise ValueError("webhook timeout_seconds must be an integer between 1 and 60")

    if "smtp_port" in config:
        smtp_port = config["smtp_port"]
        if not isinstance(smtp_port, int) or smtp_port < 1 or smtp_port > 65535:
            raise ValueError("email smtp_port must be an integer between 1 and 65535")

    if "to" in config:
        recipients = config["to"]
        if (
            not isinstance(recipients, list)
            or not recipients
            or not all(_is_non_empty_string(item) for item in recipients)
        ):
            raise ValueError("email to must be a non-empty list of email addresses")

    for field in ("routing_key", "signing_secret", "smtp_password", "smtp_user", "smtp_host", "from_email", "reply_to"):
        if field in config and not _is_non_empty_string(config[field]):
            raise ValueError(f"{field} must be a non-empty string")


def _validate_http_url(field: str, value: Any) -> None:
    if not _is_non_empty_string(value):
        raise ValueError(f"{field} must be a non-empty URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTP(S) URL")


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _redact_config_value(path: tuple[str, ...], value: Any, secret_fields: frozenset[str]) -> Any:
    normalized_path = ".".join(path).lower()
    if normalized_path in secret_fields:
        return REDACTED_VALUE if not _is_empty_value(value) else value
    if isinstance(value, Mapping):
        return {key: _redact_config_value((*path, str(key)), item, secret_fields) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_config_value(path, item, secret_fields) for item in value]
    return value


def _iter_secret_values(channel_type: str, config: Mapping[str, Any] | None) -> list[str]:
    redacted_config = redact_notification_channel_config(channel_type, config)
    original_config = validate_notification_channel_config(channel_type, config)
    secret_values: list[str] = []
    _collect_redacted_values(original_config, redacted_config, secret_values)
    return secret_values


def _iter_secret_values_for_error(channel_type: str, config: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(config, Mapping):
        return []
    try:
        schema = CHANNEL_CONFIG_SCHEMAS[normalize_notification_channel_type(channel_type)]
    except ValueError:
        return []

    secret_values: list[str] = []
    for secret_field in schema.secret_fields:
        value = _get_path_value(config, tuple(secret_field.split(".")))
        _collect_string_values(value, secret_values)
    return secret_values


def _get_path_value(config: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = config
    for segment in path:
        if not isinstance(current, Mapping):
            return None
        current = _get_mapping_value_case_insensitive(current, segment)
    return current


def _get_mapping_value_case_insensitive(config: Mapping[str, Any], key: str) -> Any:
    if key in config:
        return config[key]
    normalized_key = key.lower()
    for candidate_key, value in config.items():
        if str(candidate_key).lower() == normalized_key:
            return value
    return None


def _collect_string_values(value: Any, values: list[str]) -> None:
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, Mapping):
        values.extend(str(item) for item in value.values() if isinstance(item, str))
    elif isinstance(value, list):
        values.extend(str(item) for item in value if isinstance(item, str))


def _collect_redacted_values(original: Any, redacted: Any, values: list[str]) -> None:
    if redacted == REDACTED_VALUE:
        if isinstance(original, str):
            values.append(original)
        elif isinstance(original, Mapping):
            values.extend(str(value) for value in original.values() if isinstance(value, str))
        elif isinstance(original, list):
            values.extend(str(value) for value in original if isinstance(value, str))
        return
    if isinstance(original, Mapping) and isinstance(redacted, Mapping):
        for key, value in original.items():
            _collect_redacted_values(value, redacted.get(key), values)
    elif isinstance(original, list) and isinstance(redacted, list):
        for index, value in enumerate(original):
            if index < len(redacted):
                _collect_redacted_values(value, redacted[index], values)
