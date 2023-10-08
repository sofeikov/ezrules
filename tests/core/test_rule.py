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
    rule = Rule(logic=rule_logic)
    rule_output = rule(rule_input)
    assert rule_output == expected_output
