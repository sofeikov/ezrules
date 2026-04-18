import pytest

from ezrules.core.type_casting import (
    FieldCastConfig,
    FieldType,
    RequiredFieldError,
    find_missing_fields,
    normalize_event,
)


def test_normalize_event_casts_nested_field_paths():
    result = normalize_event(
        {"customer": {"profile": {"age": "21", "score": "9.5"}}},
        [
            FieldCastConfig(field_name="customer.profile.age", field_type=FieldType.INTEGER, required=True),
            FieldCastConfig(field_name="customer.profile.score", field_type=FieldType.FLOAT),
        ],
    )

    assert result == {"customer": {"profile": {"age": 21, "score": 9.5}}}


def test_normalize_event_rejects_missing_nested_required_field():
    with pytest.raises(RequiredFieldError, match="customer.profile.age"):
        normalize_event(
            {"customer": {"profile": {}}},
            [FieldCastConfig(field_name="customer.profile.age", field_type=FieldType.INTEGER, required=True)],
        )


def test_find_missing_fields_supports_nested_paths():
    missing = find_missing_fields(
        {"customer": {"profile": {"age": None}}, "merchant": {"id": "m_1"}},
        ["customer.profile.age", "merchant.id", "merchant.country"],
    )

    assert missing == ["customer.profile.age", "merchant.country"]
