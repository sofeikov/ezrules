from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any


def split_field_path(field_name: str) -> tuple[str, ...]:
    return tuple(field_name.split("."))


def get_field_value(event: Mapping[str, Any], field_name: str) -> Any:
    current: Any = event
    for segment in split_field_path(field_name):
        if not isinstance(current, Mapping) or segment not in current:
            raise KeyError(field_name)
        current = current[segment]
    return current


def set_field_value(target: dict[str, Any], field_name: str, value: Any) -> None:
    current: dict[str, Any] = target
    segments = split_field_path(field_name)

    for segment in segments[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = next_value

    current[segments[-1]] = value


def iter_field_paths(event_data: Mapping[str, Any]) -> Iterator[tuple[str, Any]]:
    for field_name, value in event_data.items():
        current_path = str(field_name)
        yield current_path, value
        if isinstance(value, Mapping):
            for child_path, child_value in iter_field_paths(value):
                yield f"{current_path}.{child_path}", child_value
