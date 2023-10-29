import pytest
from core.rule_helpers import DollarNotationConverter


@pytest.mark.parametrize(
    "input_code, expected_output",
    [
        (
            '"This is $text within quotes."',
            '"This is $text within quotes."',
        ),  # Dollar notation within quoted string
        (
            '$variable inside "$quoted string".',
            't["variable"] inside "$quoted string".',
        ),  # Dollar notation and quoted string
        (
            '"No $variable inside quotes."',
            '"No $variable inside quotes."',
        ),  # No dollar notation within quoted string
        (
            '$1invalid inside "$quoted $string".',
            '$1invalid inside "$quoted $string".',
        ),  # Invalid variable inside quoted string
        (
            '$@ inside "$quoted $string".',
            '$@ inside "$quoted $string".',
        ),  # Invalid variable inside quoted string
    ],
)
def test_replace_dollar_notation_quotes(input_code, expected_output):
    converter = DollarNotationConverter()
    result = converter.transform_rule(input_code)
    assert result == expected_output


@pytest.mark.parametrize(
    "input_code, expected_output",
    [
        ("$variable", 't["variable"]'),
        (
            "This is $text with $multiple $variables.",
            'This is t["text"] with t["multiple"] t["variables"].',
        ),
        (
            "$1invalid",
            "$1invalid",
        ),  # Dollar notation should not be applied to invalid variable names
        ("$@", "$@"),  # Dollar notation should not be applied to invalid variable names
        ("No variables here.", "No variables here."),  # No dollar notation in the input
    ],
)
def test_replace_dollar_notation(input_code, expected_output):
    converter = DollarNotationConverter()
    result = converter.transform_rule(input_code)
    assert result == expected_output
