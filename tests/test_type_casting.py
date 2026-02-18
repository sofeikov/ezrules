from datetime import datetime

import pytest

from ezrules.core.type_casting import CastError, FieldCastConfig, FieldType, cast_event


# ---------------------------------------------------------------------------
# Integer casting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ("1500", 1500),
        (1500, 1500),
        (1500.9, 1500),
        ("0", 0),
    ],
)
def test_cast_integer(value, expected):
    config = FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)
    result = cast_event({"amount": value}, [config])
    assert result["amount"] == expected
    assert isinstance(result["amount"], int)


def test_cast_integer_fails_on_non_numeric_string():
    config = FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)
    with pytest.raises(CastError, match="amount"):
        cast_event({"amount": "not_a_number"}, [config])


# ---------------------------------------------------------------------------
# Float casting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ("1500.5", 1500.5),
        (1500, 1500.0),
        ("0.0", 0.0),
    ],
)
def test_cast_float(value, expected):
    config = FieldCastConfig(field_name="score", field_type=FieldType.FLOAT)
    result = cast_event({"score": value}, [config])
    assert result["score"] == pytest.approx(expected)
    assert isinstance(result["score"], float)


def test_cast_float_fails_on_non_numeric_string():
    config = FieldCastConfig(field_name="score", field_type=FieldType.FLOAT)
    with pytest.raises(CastError, match="score"):
        cast_event({"score": "bad"}, [config])


# ---------------------------------------------------------------------------
# String casting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        (123, "123"),
        (12.5, "12.5"),
        ("already_string", "already_string"),
        (True, "True"),
    ],
)
def test_cast_string(value, expected):
    config = FieldCastConfig(field_name="code", field_type=FieldType.STRING)
    result = cast_event({"code": value}, [config])
    assert result["code"] == expected
    assert isinstance(result["code"], str)


# ---------------------------------------------------------------------------
# Boolean casting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        (True, True),
        (False, False),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("1", True),
        ("false", False),
        ("False", False),
        ("no", False),
        ("0", False),
        (1, True),
        (0, False),
    ],
)
def test_cast_boolean(value, expected):
    config = FieldCastConfig(field_name="flag", field_type=FieldType.BOOLEAN)
    result = cast_event({"flag": value}, [config])
    assert result["flag"] is expected


def test_cast_boolean_fails_on_ambiguous_value():
    config = FieldCastConfig(field_name="flag", field_type=FieldType.BOOLEAN)
    with pytest.raises(CastError, match="flag"):
        cast_event({"flag": "maybe"}, [config])


# ---------------------------------------------------------------------------
# Datetime casting — ISO 8601 (default)
# ---------------------------------------------------------------------------


def test_cast_datetime_iso_default():
    config = FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME)
    result = cast_event({"ts": "2024-01-15T10:30:00"}, [config])
    assert result["ts"] == datetime(2024, 1, 15, 10, 30, 0)


def test_cast_datetime_iso_date_only():
    config = FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME)
    result = cast_event({"ts": "2024-01-15"}, [config])
    assert result["ts"].year == 2024
    assert result["ts"].month == 1
    assert result["ts"].day == 15


def test_cast_datetime_iso_fails_on_bad_value():
    config = FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME)
    with pytest.raises(CastError, match="ISO 8601"):
        cast_event({"ts": "15/01/2024"}, [config])


# ---------------------------------------------------------------------------
# Datetime casting — custom format
# ---------------------------------------------------------------------------


def test_cast_datetime_custom_format():
    config = FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME, datetime_format="%d/%m/%Y")
    result = cast_event({"ts": "15/01/2024"}, [config])
    assert result["ts"] == datetime(2024, 1, 15)


def test_cast_datetime_custom_format_fails_on_mismatch():
    config = FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME, datetime_format="%d/%m/%Y")
    with pytest.raises(CastError, match="%d/%m/%Y"):
        cast_event({"ts": "2024-01-15"}, [config])


# ---------------------------------------------------------------------------
# Compare-as-is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["string", 123, 1.5, True, None, [1, 2, 3], {"nested": "dict"}])
def test_compare_as_is_passes_through_any_type(value):
    config = FieldCastConfig(field_name="data", field_type=FieldType.COMPARE_AS_IS)
    result = cast_event({"data": value}, [config])
    assert result["data"] == value


# ---------------------------------------------------------------------------
# cast_event — mixed configured and unconfigured fields
# ---------------------------------------------------------------------------


def test_unconfigured_fields_pass_through_unchanged():
    configs = [FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)]
    event = {"amount": "500", "country": "US", "tags": [1, 2, 3]}
    result = cast_event(event, configs)
    assert result["amount"] == 500
    assert result["country"] == "US"
    assert result["tags"] == [1, 2, 3]


def test_cast_event_empty_configs_returns_event_unchanged():
    event = {"amount": "500", "country": "US"}
    result = cast_event(event, [])
    assert result == event


def test_cast_event_multiple_configs():
    configs = [
        FieldCastConfig(field_name="amount", field_type=FieldType.FLOAT),
        FieldCastConfig(field_name="active", field_type=FieldType.BOOLEAN),
        FieldCastConfig(field_name="ts", field_type=FieldType.DATETIME),
    ]
    event = {"amount": "1500.5", "active": "true", "ts": "2024-06-01T00:00:00", "country": "US"}
    result = cast_event(event, configs)
    assert result["amount"] == pytest.approx(1500.5)
    assert result["active"] is True
    assert result["ts"] == datetime(2024, 6, 1)
    assert result["country"] == "US"
