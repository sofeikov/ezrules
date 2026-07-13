from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ezrules.backend.features import _compute_aggregate
from tests.feature_math_oracle import aggregate_numeric, count_distinct

pytestmark = pytest.mark.property

PROPERTY_SETTINGS = settings(max_examples=100, derandomize=True, database=None)
AS_OF = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
FINITE_NUMBERS = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False, width=64)
SCALARS = st.one_of(st.integers(-1000, 1000), st.text(max_size=12), st.booleans(), st.none())


def _aggregate(aggregation: str, values: list[Any], *, null_handling: str = "exclude") -> Any:
    feature = SimpleNamespace(
        aggregation_type=aggregation,
        source_field="value",
        null_handling=null_handling,
    )
    events = [SimpleNamespace(event_data={"value": value}, effective_at=AS_OF) for value in values]
    result, _invalid_count, _aggregate_overflow = _compute_aggregate(feature, events, as_of=AS_OF)
    return result


@PROPERTY_SETTINGS
@given(values=st.lists(FINITE_NUMBERS, min_size=1, max_size=40))
def test_numeric_aggregates_match_independent_oracle_and_ignore_order(values):
    reversed_values = list(reversed(values))
    for aggregation in ("sum", "avg", "min", "max", "stddev"):
        expected = aggregate_numeric(aggregation, values)
        assert expected is not None
        result = _aggregate(aggregation, values)
        reversed_result = _aggregate(aggregation, reversed_values)
        assert result == pytest.approx(float(expected), rel=1e-12, abs=1e-9)
        assert reversed_result == pytest.approx(result, rel=1e-12, abs=1e-9)


@PROPERTY_SETTINGS
@given(values=st.lists(FINITE_NUMBERS, min_size=1, max_size=40))
def test_average_stays_between_minimum_and_maximum(values):
    minimum = _aggregate("min", values)
    average = _aggregate("avg", values)
    maximum = _aggregate("max", values)

    assert minimum <= average <= maximum


@PROPERTY_SETTINGS
@given(value=FINITE_NUMBERS, count=st.integers(min_value=1, max_value=40))
def test_population_standard_deviation_is_zero_for_identical_values(value, count):
    assert _aggregate("stddev", [value] * count) == pytest.approx(0.0)


@PROPERTY_SETTINGS
@given(values=st.lists(SCALARS, max_size=40))
def test_count_distinct_is_bounded_by_count_and_uses_typed_identity(values):
    assert _aggregate("count_distinct", values) == count_distinct(values)
    assert 0 <= _aggregate("count_distinct", values) <= _aggregate("count", values)


@PROPERTY_SETTINGS
@given(
    left=st.lists(FINITE_NUMBERS, max_size=30),
    right=st.lists(FINITE_NUMBERS, max_size=30),
)
def test_sum_is_stable_when_history_is_partitioned(left, right):
    combined = _aggregate("sum", left + right) or 0.0
    left_sum = _aggregate("sum", left) or 0.0
    right_sum = _aggregate("sum", right) or 0.0

    assert combined == pytest.approx(left_sum + right_sum, rel=1e-12, abs=1e-9)
