import pytest

from ezrules.backend.rule_validation import validate_rule_source
from ezrules.core.rule import ReservedRuleIdentifierError, Rule, RuleGeneratorSyntaxError
from ezrules.models.backend_core import AllowedOutcome


@pytest.mark.parametrize(
    "logic",
    [
        "yield !HOLD",
        "yield from (!HOLD,)",
        "if False:\n    yield !HOLD\nreturn None",
    ],
)
def test_outer_rule_generator_syntax_is_rejected(logic: str) -> None:
    rule = Rule(rid="generator-contract", logic=logic)

    with pytest.raises(RuleGeneratorSyntaxError, match="cannot use `yield`"):
        rule.validate_return_contract()


def test_nested_helper_generators_do_not_make_the_outer_rule_a_generator() -> None:
    rule = Rule(
        rid="nested-generator",
        logic=(
            "def values():\n    yield 1\nfor value in values():\n    if value == 1:\n        return !HOLD\nreturn None"
        ),
    )

    rule.validate_return_contract()

    assert rule({}) == "HOLD"


@pytest.mark.parametrize(
    "logic",
    [
        'return __ezrules_outcome__("NOT_CONFIGURED")',
        'return __ezrules_outcome__("HOLD")',
        'return __ezrules_outcome__("")',
    ],
)
def test_hand_written_outcome_helpers_are_rejected_before_conversion(logic: str) -> None:
    with pytest.raises(ReservedRuleIdentifierError, match="Identifier '__ezrules_outcome__' is reserved"):
        Rule(rid="reserved-helper", logic=logic)


def test_reserved_helper_text_in_comments_and_strings_is_inert() -> None:
    rule = Rule(
        rid="reserved-helper-text",
        logic=(
            "# __ezrules_outcome__ is an implementation detail\n"
            'note = "__ezrules_outcome__"\n'
            "if note:\n"
            "    return !HOLD\n"
            "return None"
        ),
    )

    rule.validate_return_contract()

    assert rule({}) == "HOLD"


def test_bang_outcome_syntax_remains_valid() -> None:
    rule = Rule(rid="bang-outcome", logic="return !HOLD")

    rule.validate_return_contract()

    assert rule({}) == "HOLD"


@pytest.mark.parametrize(
    ("logic", "message", "line"),
    [
        ("if False:\n    yield !HOLD\nreturn None", "cannot use `yield`", 2),
        ('return __ezrules_outcome__("HOLD")', "reserved", 1),
    ],
)
def test_verify_reports_contract_bypasses_as_source_diagnostics(session, logic: str, message: str, line: int) -> None:
    session.add(AllowedOutcome(outcome_name="HOLD", severity_rank=1, o_id=1))
    session.commit()

    validation = validate_rule_source(session, 1, logic)

    assert validation.compiled_rule is None
    assert validation.response.valid is False
    assert len(validation.response.errors) == 1
    assert message in validation.response.errors[0].message
    assert validation.response.errors[0].line == line
    assert validation.response.errors[0].column is not None
