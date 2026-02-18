from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class FieldType(StrEnum):
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    COMPARE_AS_IS = "compare_as_is"


@dataclass
class FieldCastConfig:
    field_name: str
    field_type: FieldType
    datetime_format: str | None = None  # strptime format string; None means ISO 8601


class CastError(Exception):
    """Raised when a field value cannot be cast to the configured type."""


def _cast_value(value: Any, config: FieldCastConfig) -> Any:
    if config.field_type == FieldType.COMPARE_AS_IS:
        return value

    if config.field_type == FieldType.INTEGER:
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            raise CastError(f"Cannot cast field '{config.field_name}' value {value!r} to integer") from e

    if config.field_type == FieldType.FLOAT:
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            raise CastError(f"Cannot cast field '{config.field_name}' value {value!r} to float") from e

    if config.field_type == FieldType.STRING:
        return str(value)

    if config.field_type == FieldType.BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True
            if value.lower() in ("false", "0", "no"):
                return False
        if isinstance(value, int):
            return bool(value)
        raise CastError(f"Cannot cast field '{config.field_name}' value {value!r} to boolean")

    if config.field_type == FieldType.DATETIME:
        if config.datetime_format is None:
            try:
                return datetime.fromisoformat(str(value))
            except (ValueError, TypeError) as e:
                raise CastError(
                    f"Cannot cast field '{config.field_name}' value {value!r} to datetime: expected ISO 8601 format"
                ) from e
        try:
            return datetime.strptime(str(value), config.datetime_format)
        except (ValueError, TypeError) as e:
            raise CastError(
                f"Cannot cast field '{config.field_name}' value {value!r} to datetime: expected format '{config.datetime_format}'"
            ) from e

    raise CastError(f"Unknown field type: {config.field_type}")  # pragma: no cover


def cast_event(event: dict[str, Any], configs: list[FieldCastConfig]) -> dict[str, Any]:
    """Apply configured type casts to an event dict.

    Fields not present in configs pass through unchanged (compare-as-is default).
    Raises CastError if a configured field value cannot be cast to the configured type.
    """
    config_map = {c.field_name: c for c in configs}
    return {key: _cast_value(value, config_map[key]) if key in config_map else value for key, value in event.items()}
