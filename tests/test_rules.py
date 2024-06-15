import pytest
from ezrules.core.rule import Rule


@pytest.mark.parametrize(
    ["logic", "input", "expected_result"],
    [
        ("if $amount>900:\n\treturn 'HOLD'", {"amount": 950}, "HOLD"),
        (
            "if $user_data['total'] > 900:\n\treturn 'HOLD'",
            {"user_data": {"total": 1000}},
            "HOLD",
        ),
        (
            "if $amount>900 and $user_age<35:\n\treturn 'CANCEL'",
            {"amount": 1000, "user_age": 1},
            "CANCEL",
        ),
    ],
)
def test_can_use_dollar_sign_notation(logic, input, expected_result):
    rule = Rule(rid="1", logic=logic)
    outcome = rule(input)
    assert outcome == expected_result


@pytest.mark.parametrize(
    ["logic", "input", "expected_result"],
    [
        ("if $country in @NACountries:\n\treturn 'HOLD'", {"country": "US"}, "HOLD"),
    ],
)
def test_can_use_custom_lists(logic, input, expected_result):
    rule = Rule(rid="1", logic=logic)
    outcome = rule(input)
    assert outcome == expected_result
