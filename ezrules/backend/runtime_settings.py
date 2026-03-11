"""Helpers for runtime-configurable system settings stored in the database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ezrules.models.backend_core import RuntimeSetting
from ezrules.settings import app_settings

RULE_QUALITY_LOOKBACK_DAYS_KEY = "rule_quality_lookback_days"

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


_RUNTIME_SETTING_SPECS: dict[str, RuntimeSettingSpec] = {
    RULE_QUALITY_LOOKBACK_DAYS_KEY: RuntimeSettingSpec(
        key=RULE_QUALITY_LOOKBACK_DAYS_KEY,
        value_type=_RUNTIME_VALUE_TYPE_INT,
        default=app_settings.RULE_QUALITY_LOOKBACK_DAYS,
        min_value=1,
        max_value=3650,
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
        return str(value)

    if spec.value_type == _RUNTIME_VALUE_TYPE_JSON:
        return value

    raise ValueError(f"Unsupported runtime setting value type: {spec.value_type}")


def _get_spec(key: str) -> RuntimeSettingSpec:
    spec = _RUNTIME_SETTING_SPECS.get(key)
    if spec is None:
        raise KeyError(f"Unknown runtime setting key: {key}")
    return spec


def get_runtime_setting(db: Any, key: str) -> Any:
    spec = _get_spec(key)
    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    if setting is None:
        return spec.default

    try:
        parsed = _parse_value(setting.value_type, setting.value)
        return _coerce_to_spec(spec, parsed)
    except Exception:
        return spec.default


def set_runtime_setting(db: Any, key: str, value: Any) -> None:
    spec = _get_spec(key)
    normalized = _coerce_to_spec(spec, value)
    serialized = _serialize_value(spec.value_type, normalized)

    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    if setting is None:
        setting = RuntimeSetting(
            key=key,
            value_type=spec.value_type,
            value=serialized,
        )
        db.add(setting)
        return

    setting.value_type = spec.value_type
    setting.value = serialized


def get_rule_quality_lookback_days(db: Any) -> int:
    return int(get_runtime_setting(db, RULE_QUALITY_LOOKBACK_DAYS_KEY))


def set_rule_quality_lookback_days(db: Any, value: int) -> None:
    set_runtime_setting(db, RULE_QUALITY_LOOKBACK_DAYS_KEY, value)
