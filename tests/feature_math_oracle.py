"""Independent reference calculations for computed-feature contract tests."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def decimal_number(value: Any, *, null_handling: str = "exclude") -> Decimal | None:
    if value is None:
        return Decimal(0) if null_handling == "zero" else None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def numeric_values(values: Iterable[Any], *, null_handling: str = "exclude") -> list[Decimal]:
    numbers = [decimal_number(value, null_handling=null_handling) for value in values]
    return [number for number in numbers if number is not None]


def aggregate_numeric(
    aggregation: str,
    values: Iterable[Any],
    *,
    null_handling: str = "exclude",
) -> Decimal | None:
    numbers = numeric_values(values, null_handling=null_handling)
    if not numbers:
        return None
    if aggregation == "sum":
        return sum(numbers, start=Decimal(0))
    if aggregation == "avg":
        return statistics.mean(numbers)
    if aggregation == "min":
        return min(numbers)
    if aggregation == "max":
        return max(numbers)
    if aggregation == "stddev":
        return statistics.pstdev(numbers)
    raise ValueError(f"Unsupported numeric aggregation: {aggregation}")


def count_distinct(values: Iterable[Any]) -> int:
    identities: set[tuple[str, str]] = set()
    for value in values:
        if value is None or isinstance(value, dict | list):
            continue
        if isinstance(value, bool):
            identities.add(("boolean", str(value).lower()))
        elif isinstance(value, str):
            identities.add(("string", value))
        elif isinstance(value, int | float):
            number = decimal_number(value)
            if number is not None:
                identities.add(("number", format(number.normalize(), "f")))
    return len(identities)


def days_since_first_seen(as_of: datetime, effective_times: Iterable[datetime]) -> int | None:
    normalized = [as_utc(value) for value in effective_times]
    if not normalized:
        return None
    return max(0, (as_utc(as_of) - min(normalized)).days)
