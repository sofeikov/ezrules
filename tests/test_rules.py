import pytest

from ezrules.core.rule import OutcomeReturnSyntaxError, Rule


@pytest.mark.parametrize(
    ["logic", "input", "expected_result"],
    [
        ("if $amount>900:\n\treturn !HOLD", {"amount": 950}, "HOLD"),
        (
            "if $user_data['total'] > 900:\n\treturn !HOLD",
            {"user_data": {"total": 1000}},
            "HOLD",
        ),
        (
            "if $amount>900 and $user_age<35:\n\treturn !CANCEL",
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
        ("if $country in @NACountries:\n\treturn !HOLD", {"country": "US"}, "HOLD"),
    ],
)
def test_can_use_custom_lists(session, logic, input, expected_result):
    # Application context is set up by the session fixture
    rule = Rule(rid="1", logic=logic)
    outcome = rule(input)
    assert outcome == expected_result


@pytest.mark.parametrize(
    "logic",
    [
        'if True:\n\treturn ("HOLD")',
        'value = "HOLD"\nreturn value',
        'return "HOLD" if True else None',
    ],
)
def test_rejects_indirect_or_quoted_outcome_returns(logic):
    with pytest.raises(OutcomeReturnSyntaxError):
        Rule(rid="1", logic=logic)
