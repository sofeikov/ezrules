import pytest

from ezrules.core.type_casting import (
    FieldCastConfig,
    FieldType,
    RequiredFieldError,
    find_missing_fields,
    normalize_event,
)


def test_normalize_event_rejects_missing_required_field():
    configs = [FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER, required=True)]

    with pytest.raises(RequiredFieldError, match="amount"):
        normalize_event({"country": "US"}, configs)


def test_normalize_event_rejects_null_required_field():
    configs = [FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER, required=True)]

    with pytest.raises(RequiredFieldError, match="amount"):
        normalize_event({"amount": None}, configs)


def test_normalize_event_skips_casting_null_optional_field():
    configs = [FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)]

    result = normalize_event({"amount": None, "country": "US"}, configs)

    assert result["amount"] is None
    assert result["country"] == "US"


def test_normalize_event_casts_present_non_null_values():
    configs = [
        FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER, required=True),
        FieldCastConfig(field_name="score", field_type=FieldType.FLOAT),
    ]

    result = normalize_event({"amount": "150", "score": "9.5"}, configs)

    assert result["amount"] == 150
    assert result["score"] == pytest.approx(9.5)


def test_find_missing_fields_treats_null_as_missing():
    missing = find_missing_fields({"amount": None, "country": "US"}, ["amount", "country", "merchant_id"])

    assert missing == ["amount", "merchant_id"]
