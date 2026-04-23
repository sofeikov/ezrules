"""Helpers for runtime-configurable system settings stored in the database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ezrules.models.backend_core import RuntimeSetting
from ezrules.settings import app_settings

AUTO_PROMOTE_ACTIVE_RULE_UPDATES_KEY = "auto_promote_active_rule_updates"
AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT = False
STRICT_MODE_ENABLED_KEY = "strict_mode_enabled"
STRICT_MODE_ENABLED_DEFAULT = False
MAIN_RULE_EXECUTION_MODE_KEY = "main_rule_execution_mode"
MAIN_RULE_EXECUTION_MODE_ALL_MATCHES = "all_matches"
MAIN_RULE_EXECUTION_MODE_FIRST_MATCH = "first_match"
MAIN_RULE_EXECUTION_MODE_DEFAULT = MAIN_RULE_EXECUTION_MODE_ALL_MATCHES
RULE_QUALITY_LOOKBACK_DAYS_KEY = "rule_quality_lookback_days"
NEUTRAL_OUTCOME_KEY = "neutral_outcome"
NEUTRAL_OUTCOME_DEFAULT = "RELEASE"
FIELD_TYPE_CONFIG_VERSION_KEY = "field_type_config_version"
FIELD_TYPE_CONFIG_VERSION_DEFAULT = 0
API_KEY_CACHE_VERSION_KEY = "api_key_cache_version"
API_KEY_CACHE_VERSION_DEFAULT = 0
AI_AUTHORING_PROVIDER_KEY = "ai_authoring_provider"
AI_AUTHORING_PROVIDER_DEFAULT = "openai"
AI_AUTHORING_ENABLED_KEY = "ai_authoring_enabled"
AI_AUTHORING_ENABLED_DEFAULT = True
AI_AUTHORING_MODEL_KEY = "ai_authoring_model"
AI_AUTHORING_MODEL_DEFAULT = app_settings.AI_AUTHORING_MODEL or ""
AI_AUTHORING_API_KEY_KEY = "ai_authoring_api_key"
AI_AUTHORING_API_KEY_DEFAULT = app_settings.AI_AUTHORING_API_KEY or ""

_RUNTIME_VALUE_TYPE_INT = "int"
_RUNTIME_VALUE_TYPE_FLOAT = "float"
_RUNTIME_VALUE_TYPE_BOOL = "bool"
_RUNTIME_VALUE_TYPE_STRING = "string"
_RUNTIME_VALUE_TYPE_JSON = "json"


@dataclass(frozen=True)
class RuntimeSettingSpec:
    key: str
    value_type: str
    default: Any
    min_value: int | None = None
    max_value: int | None = None
    allowed_values: tuple[Any, ...] | None = None


_RUNTIME_SETTING_SPECS: dict[str, RuntimeSettingSpec] = {
    AUTO_PROMOTE_ACTIVE_RULE_UPDATES_KEY: RuntimeSettingSpec(
        key=AUTO_PROMOTE_ACTIVE_RULE_UPDATES_KEY,
        value_type=_RUNTIME_VALUE_TYPE_BOOL,
        default=AUTO_PROMOTE_ACTIVE_RULE_UPDATES_DEFAULT,
    ),
    STRICT_MODE_ENABLED_KEY: RuntimeSettingSpec(
        key=STRICT_MODE_ENABLED_KEY,
        value_type=_RUNTIME_VALUE_TYPE_BOOL,
        default=STRICT_MODE_ENABLED_DEFAULT,
    ),
    MAIN_RULE_EXECUTION_MODE_KEY: RuntimeSettingSpec(
        key=MAIN_RULE_EXECUTION_MODE_KEY,
        value_type=_RUNTIME_VALUE_TYPE_STRING,
        default=MAIN_RULE_EXECUTION_MODE_DEFAULT,
        allowed_values=(MAIN_RULE_EXECUTION_MODE_ALL_MATCHES, MAIN_RULE_EXECUTION_MODE_FIRST_MATCH),
    ),
    RULE_QUALITY_LOOKBACK_DAYS_KEY: RuntimeSettingSpec(
        key=RULE_QUALITY_LOOKBACK_DAYS_KEY,
        value_type=_RUNTIME_VALUE_TYPE_INT,
        default=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        min_value=1,
        max_value=3650,
    ),
    NEUTRAL_OUTCOME_KEY: RuntimeSettingSpec(
        key=NEUTRAL_OUTCOME_KEY,
        value_type=_RUNTIME_VALUE_TYPE_STRING,
        default=NEUTRAL_OUTCOME_DEFAULT,
    ),
    FIELD_TYPE_CONFIG_VERSION_KEY: RuntimeSettingSpec(
        key=FIELD_TYPE_CONFIG_VERSION_KEY,
        value_type=_RUNTIME_VALUE_TYPE_INT,
        default=FIELD_TYPE_CONFIG_VERSION_DEFAULT,
        min_value=0,
    ),
    API_KEY_CACHE_VERSION_KEY: RuntimeSettingSpec(
        key=API_KEY_CACHE_VERSION_KEY,
        value_type=_RUNTIME_VALUE_TYPE_INT,
        default=API_KEY_CACHE_VERSION_DEFAULT,
        min_value=0,
    ),
    AI_AUTHORING_PROVIDER_KEY: RuntimeSettingSpec(
        key=AI_AUTHORING_PROVIDER_KEY,
        value_type=_RUNTIME_VALUE_TYPE_STRING,
        default=AI_AUTHORING_PROVIDER_DEFAULT,
        allowed_values=(AI_AUTHORING_PROVIDER_DEFAULT,),
    ),
    AI_AUTHORING_ENABLED_KEY: RuntimeSettingSpec(
        key=AI_AUTHORING_ENABLED_KEY,
        value_type=_RUNTIME_VALUE_TYPE_BOOL,
        default=AI_AUTHORING_ENABLED_DEFAULT,
    ),
    AI_AUTHORING_MODEL_KEY: RuntimeSettingSpec(
        key=AI_AUTHORING_MODEL_KEY,
        value_type=_RUNTIME_VALUE_TYPE_STRING,
        default=AI_AUTHORING_MODEL_DEFAULT,
    ),
    AI_AUTHORING_API_KEY_KEY: RuntimeSettingSpec(
        key=AI_AUTHORING_API_KEY_KEY,
        value_type=_RUNTIME_VALUE_TYPE_STRING,
        default=AI_AUTHORING_API_KEY_DEFAULT,
    ),
}


def _serialize_value(value_type: str, value: Any) -> str:
    if value_type == _RUNTIME_VALUE_TYPE_INT:
        return str(int(value))
    if value_type == _RUNTIME_VALUE_TYPE_FLOAT:
        return str(float(value))
    if value_type == _RUNTIME_VALUE_TYPE_BOOL:
        return "true" if bool(value) else "false"
    if value_type == _RUNTIME_VALUE_TYPE_STRING:
        return str(value)
    if value_type == _RUNTIME_VALUE_TYPE_JSON:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    raise ValueError(f"Unsupported runtime setting value type: {value_type}")


def _parse_value(value_type: str, raw: str) -> Any:
    if value_type == _RUNTIME_VALUE_TYPE_INT:
        return int(raw)
    if value_type == _RUNTIME_VALUE_TYPE_FLOAT:
        return float(raw)
    if value_type == _RUNTIME_VALUE_TYPE_BOOL:
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"Invalid boolean runtime setting value: {raw!r}")
    if value_type == _RUNTIME_VALUE_TYPE_STRING:
        return raw
    if value_type == _RUNTIME_VALUE_TYPE_JSON:
        return json.loads(raw)
    raise ValueError(f"Unsupported runtime setting value type: {value_type}")


def _coerce_to_spec(spec: RuntimeSettingSpec, value: Any) -> Any:
    if spec.value_type == _RUNTIME_VALUE_TYPE_INT:
        normalized = int(value)
        if spec.min_value is not None and normalized < spec.min_value:
            raise ValueError(f"{spec.key} must be >= {spec.min_value}")
        if spec.max_value is not None and normalized > spec.max_value:
            raise ValueError(f"{spec.key} must be <= {spec.max_value}")
        return normalized

    if spec.value_type == _RUNTIME_VALUE_TYPE_FLOAT:
        return float(value)

    if spec.value_type == _RUNTIME_VALUE_TYPE_BOOL:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return _parse_value(_RUNTIME_VALUE_TYPE_BOOL, value)
        if isinstance(value, int):
            return bool(value)
        raise ValueError(f"{spec.key} must be a boolean-compatible value")

    if spec.value_type == _RUNTIME_VALUE_TYPE_STRING:
        normalized = str(value).strip()
        if spec.allowed_values is not None and normalized not in spec.allowed_values:
            allowed = ", ".join(str(item) for item in spec.allowed_values)
            raise ValueError(f"{spec.key} must be one of: {allowed}")
        return normalized

    if spec.value_type == _RUNTIME_VALUE_TYPE_JSON:
        return value

    raise ValueError(f"Unsupported runtime setting value type: {spec.value_type}")


def _get_spec(key: str) -> RuntimeSettingSpec:
    spec = _RUNTIME_SETTING_SPECS.get(key)
    if spec is None:
        raise KeyError(f"Unknown runtime setting key: {key}")
    return spec


def get_runtime_setting(db: Any, key: str, org_id: int) -> Any:
    spec = _get_spec(key)
    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == key, RuntimeSetting.o_id == org_id).first()
    if setting is None:
        return spec.default

    try:
        parsed = _parse_value(setting.value_type, setting.value)
        return _coerce_to_spec(spec, parsed)
    except Exception:
        return spec.default


def set_runtime_setting(db: Any, key: str, value: Any, org_id: int) -> None:
    spec = _get_spec(key)
    normalized = _coerce_to_spec(spec, value)
    serialized = _serialize_value(spec.value_type, normalized)

    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == key, RuntimeSetting.o_id == org_id).first()
    if setting is None:
        setting = RuntimeSetting(
            key=key,
            o_id=org_id,
            value_type=spec.value_type,
            value=serialized,
        )
        db.add(setting)
        return

    setting.value_type = spec.value_type
    setting.value = serialized


def get_rule_quality_lookback_days(db: Any, org_id: int) -> int:
    return int(get_runtime_setting(db, RULE_QUALITY_LOOKBACK_DAYS_KEY, org_id))


def get_auto_promote_active_rule_updates(db: Any, org_id: int) -> bool:
    return bool(get_runtime_setting(db, AUTO_PROMOTE_ACTIVE_RULE_UPDATES_KEY, org_id))


def get_strict_mode_enabled(db: Any, org_id: int) -> bool:
    return bool(get_runtime_setting(db, STRICT_MODE_ENABLED_KEY, org_id))


def get_main_rule_execution_mode(db: Any, org_id: int) -> str:
    return str(get_runtime_setting(db, MAIN_RULE_EXECUTION_MODE_KEY, org_id)).strip()


def get_neutral_outcome(db: Any, org_id: int) -> str:
    return str(get_runtime_setting(db, NEUTRAL_OUTCOME_KEY, org_id)).strip().upper()


def set_rule_quality_lookback_days(db: Any, value: int, org_id: int) -> None:
    set_runtime_setting(db, RULE_QUALITY_LOOKBACK_DAYS_KEY, value, org_id)


def set_auto_promote_active_rule_updates(db: Any, value: bool, org_id: int) -> None:
    set_runtime_setting(db, AUTO_PROMOTE_ACTIVE_RULE_UPDATES_KEY, value, org_id)


def set_strict_mode_enabled(db: Any, value: bool, org_id: int) -> None:
    set_runtime_setting(db, STRICT_MODE_ENABLED_KEY, value, org_id)


def set_main_rule_execution_mode(db: Any, value: str, org_id: int) -> None:
    set_runtime_setting(db, MAIN_RULE_EXECUTION_MODE_KEY, value.strip(), org_id)


def set_neutral_outcome(db: Any, value: str, org_id: int) -> None:
    set_runtime_setting(db, NEUTRAL_OUTCOME_KEY, value.strip().upper(), org_id)


def get_field_type_config_version(db: Any, org_id: int) -> int:
    return int(get_runtime_setting(db, FIELD_TYPE_CONFIG_VERSION_KEY, org_id))


def bump_field_type_config_version(db: Any, org_id: int) -> int:
    next_version = get_field_type_config_version(db, org_id) + 1
    set_runtime_setting(db, FIELD_TYPE_CONFIG_VERSION_KEY, next_version, org_id)
    return next_version


def get_api_key_cache_version(db: Any, org_id: int) -> int:
    return int(get_runtime_setting(db, API_KEY_CACHE_VERSION_KEY, org_id))


def bump_api_key_cache_version(db: Any, org_id: int) -> int:
    next_version = get_api_key_cache_version(db, org_id) + 1
    set_runtime_setting(db, API_KEY_CACHE_VERSION_KEY, next_version, org_id)
    return next_version


def get_ai_authoring_provider(db: Any, org_id: int) -> str:
    return str(get_runtime_setting(db, AI_AUTHORING_PROVIDER_KEY, org_id)).strip().lower()


def get_ai_authoring_enabled(db: Any, org_id: int) -> bool:
    return bool(get_runtime_setting(db, AI_AUTHORING_ENABLED_KEY, org_id))


def get_ai_authoring_model(db: Any, org_id: int) -> str:
    return str(get_runtime_setting(db, AI_AUTHORING_MODEL_KEY, org_id)).strip()


def get_ai_authoring_api_key(db: Any, org_id: int) -> str:
    return str(get_runtime_setting(db, AI_AUTHORING_API_KEY_KEY, org_id))


def has_ai_authoring_api_key(db: Any, org_id: int) -> bool:
    return bool(get_ai_authoring_api_key(db, org_id).strip())


def set_ai_authoring_provider(db: Any, value: str, org_id: int) -> None:
    set_runtime_setting(db, AI_AUTHORING_PROVIDER_KEY, value.strip().lower(), org_id)


def set_ai_authoring_enabled(db: Any, value: bool, org_id: int) -> None:
    set_runtime_setting(db, AI_AUTHORING_ENABLED_KEY, value, org_id)


def set_ai_authoring_model(db: Any, value: str, org_id: int) -> None:
    set_runtime_setting(db, AI_AUTHORING_MODEL_KEY, value.strip(), org_id)


def set_ai_authoring_api_key(db: Any, value: str, org_id: int) -> None:
    set_runtime_setting(db, AI_AUTHORING_API_KEY_KEY, value, org_id)
