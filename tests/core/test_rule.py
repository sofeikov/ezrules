import pytest
from core.rule import Rule


@pytest.mark.parametrize(
    ["rule_logic", "rule_input", "expected_output"],
    [
        ("return 1", {}, 1),
        (
            """
if t["a"] > 3:
    return "CANCEL"
return "RELEASE"
    """,
            {"a": 20},
            "CANCEL",
        ),
        (
            """
if t["a"] > 30:
    return "CANCEL"
return "RELEASE"
        """,
            {"a": 20},
            "RELEASE",
        ),
        (
            """
if 30 < t["a"]:
    return "CANCEL"
return "RELEASE"
        """,
            {"a": 20},
            "RELEASE",
        ),
        (
            """
if t["a"] > t["b"]:
    return "CANCEL"
return "RELEASE"
        """,
            {"a": 20, "b": 10},
            "CANCEL",
        ),
    ],
)
def test_rule_does_whats_expected(rule_logic, rule_input, expected_output):
    rule = Rule(rid="", logic=rule_logic)
    rule_output = rule(rule_input)
    assert rule_output == expected_output


@pytest.mark.parametrize(
    ["rule_logic", "expected_params"],
    [
        (
            """
if t["amount"] == 3:
    return "CANCEL"
            """,
            {"amount"},
        ),
        (
            """
if t["amount"] == t["previous_amount"]:
    return "CANCEL"
            """,
            {"amount", "previous_amount"},
        ),
        (
            """
if t["amounts"]["first"] == t["previous_amount"] + 50:
    return "CANCEL"
    """,
            {"amounts", "previous_amount"},
        ),
    ],
)
def test_extract_params_from_rule(rule_logic, expected_params):
    rule = Rule(rid="", logic=rule_logic)
    params = rule.get_rule_params()
    assert params == expected_params
