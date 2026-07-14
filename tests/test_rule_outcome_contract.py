from typing import Any

import pytest

from ezrules.backend.rule_validation import validate_rule_source
from ezrules.core.rule import OutcomeReturnSyntaxError, Rule
from ezrules.models.backend_core import AllowedOutcome, FieldObservation


@pytest.mark.parametrize(
    ("logic", "event", "expected"),
    [
        ("pass", {}, None),
        ("return", {}, None),
        ("return None", {}, None),
        ("return !HOLD", {}, "HOLD"),
        ("return (!needs_review)", {}, "NEEDS_REVIEW"),
        ("def eligible():\n    return True\nif eligible():\n    return !HOLD", {}, "HOLD"),
        ("if $amount > 100:\n    return !HOLD\nreturn None", {"amount": 50}, None),
        ("if $amount > 100:\n    return !HOLD\nreturn None", {"amount": 150}, "HOLD"),
    ],
)
def test_rule_returns_accept_only_no_result_or_direct_outcome(
    logic: str, event: dict[str, Any], expected: str | None
) -> None:
    rule = Rule(rid="contract", logic=logic)

    rule.validate_return_contract()

    assert rule(event) == expected


@pytest.mark.parametrize(
    "return_expression",
    [
        "True",
        "False",
        "0",
        "-1",
        "1.5",
        '"HOLD"',
        "[]",
        "{}",
        "set()",
        'str("HOLD")',
        't["outcome"]',
        "f\"{t['outcome']}\"",
        "[value for value in t.values()]",
        "(outcome := None)",
        "lambda: None",
        "!HOLD if True else None",
    ],
)
def test_rule_returns_reject_every_other_expression(return_expression: str) -> None:
    with pytest.raises(OutcomeReturnSyntaxError, match="return !"):
        Rule(rid="contract", logic=f"return {return_expression}").validate_return_contract()


def test_rule_returns_reject_indirect_outcome_helpers() -> None:
    with pytest.raises(OutcomeReturnSyntaxError, match="return !"):
        Rule(rid="contract", logic="outcome = !HOLD\nreturn outcome").validate_return_contract()


def test_persisted_rule_validation_accepts_configured_direct_outcomes(session) -> None:
    session.add(AllowedOutcome(outcome_name="HOLD", severity_rank=1, o_id=1))
    session.commit()

    validation = validate_rule_source(session, 1, "if $amount > 100:\n    return !HOLD\nreturn None")

    assert validation.compiled_rule is not None
    assert validation.response.valid is True
    assert validation.response.params == ["amount"]
    assert validation.response.referenced_outcomes == ["HOLD"]
    assert validation.response.errors == []


def test_persisted_rule_validation_rejects_predicate_results_without_losing_diagnostics(session) -> None:
    session.add(FieldObservation(field_name="amount", observed_json_type="int", o_id=1))
    session.commit()

    validation = validate_rule_source(session, 1, "return $amount > 100")

    assert validation.compiled_rule is None
    assert validation.response.valid is False
    assert validation.response.params == ["amount"]
    assert validation.response.warnings == []
    assert len(validation.response.errors) == 1
    assert "return !OUTCOME" in validation.response.errors[0].message
    assert validation.response.errors[0].line == 1
    assert validation.response.errors[0].column is not None
