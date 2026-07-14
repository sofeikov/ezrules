from collections.abc import Callable
from typing import Any, cast

import pytest

from ezrules.core.rule import Rule
from ezrules.core.rule_engine import (
    RULE_EXECUTION_MODE_FIRST_MATCH,
    InvalidRuleResultError,
    RuleEngine,
)


class StubRule:
    def __init__(
        self,
        *,
        r_id: int | None,
        rid: str,
        result: Any = None,
        callback: Callable[[], Any] | None = None,
    ) -> None:
        self.r_id = r_id
        self.rid = rid
        self.result = result
        self.callback = callback

    def __call__(self, _event: dict[str, Any], *, stats: dict[str, Any] | None = None) -> Any:
        del stats
        return self.callback() if self.callback is not None else self.result

    def get_rule_stats(self) -> set[str]:
        return set()


def build_engine(*rules: StubRule, execution_mode: str = "all_matches") -> RuleEngine:
    return RuleEngine(rules=cast(list[Rule], list(rules)), execution_mode=execution_mode)


def test_empty_rule_set_has_a_complete_stable_result_shape() -> None:
    assert RuleEngine(rules=[])({}) == {
        "rule_results": {},
        "all_rule_results": {},
        "outcome_counters": {},
        "outcome_set": [],
    }


def test_all_nonmatches_are_retained_only_in_all_rule_results() -> None:
    result = build_engine(
        StubRule(r_id=1, rid="first", result=None),
        StubRule(r_id=2, rid="second", result=None),
    )({})

    assert result == {
        "rule_results": {},
        "all_rule_results": {1: None, 2: None},
        "outcome_counters": {},
        "outcome_set": [],
    }


def test_zero_database_identifier_is_not_replaced_by_public_identifier() -> None:
    result = build_engine(StubRule(r_id=0, rid="fallback", result="HOLD"))({})

    assert result["rule_results"] == {0: "HOLD"}
    assert result["all_rule_results"] == {0: "HOLD"}


def test_duplicate_effective_rule_identifiers_are_rejected_before_execution() -> None:
    calls: list[str] = []
    rules = (
        StubRule(r_id=7, rid="first", callback=lambda: calls.append("first")),
        StubRule(r_id=7, rid="second", callback=lambda: calls.append("second")),
    )

    with pytest.raises(ValueError, match="Duplicate rule identifier: 7"):
        build_engine(*rules)

    assert calls == []


@pytest.mark.parametrize("execution_mode", ["", "all", "FIRST_MATCH", "unknown"])
def test_invalid_execution_modes_are_rejected(execution_mode: str) -> None:
    with pytest.raises(ValueError, match=f"Unknown rule execution mode: {execution_mode!r}"):
        build_engine(execution_mode=execution_mode)


@pytest.mark.parametrize(
    ("invalid_result", "rendered_type"),
    [
        (False, "bool"),
        (0, "int"),
        ([], "list"),
        ({}, "dict"),
        (set(), "set"),
        (lambda: "HOLD", "function"),
    ],
)
def test_non_outcome_rule_results_fail_before_aggregation(invalid_result: Any, rendered_type: str) -> None:
    engine = build_engine(StubRule(r_id=4, rid="invalid", result=invalid_result))

    with pytest.raises(
        InvalidRuleResultError,
        match=rf"Rule 4 returned {rendered_type}; expected None or a non-empty outcome string",
    ):
        engine({})


def test_empty_string_rule_result_is_rejected() -> None:
    engine = build_engine(StubRule(r_id=4, rid="invalid", result=""))

    with pytest.raises(
        InvalidRuleResultError,
        match=r"Rule 4 returned an empty outcome string; expected None or a non-empty outcome string",
    ):
        engine({})


def test_first_match_does_not_execute_rules_after_the_first_valid_outcome() -> None:
    calls: list[str] = []
    engine = build_engine(
        StubRule(r_id=1, rid="miss", callback=lambda: calls.append("miss")),
        StubRule(r_id=2, rid="hit", callback=lambda: calls.append("hit") or "HOLD"),
        StubRule(r_id=3, rid="later", callback=lambda: calls.append("later") or "CANCEL"),
        execution_mode=RULE_EXECUTION_MODE_FIRST_MATCH,
    )

    result = engine({})

    assert calls == ["miss", "hit"]
    assert result == {
        "rule_results": {2: "HOLD"},
        "all_rule_results": {1: None, 2: "HOLD"},
        "outcome_counters": {"HOLD": 1},
        "outcome_set": ["HOLD"],
    }


def test_rule_exception_aborts_without_executing_later_rules() -> None:
    calls: list[str] = []

    def fail() -> None:
        calls.append("failing")
        raise RuntimeError("rule exploded")

    engine = build_engine(
        StubRule(r_id=1, rid="first", callback=lambda: calls.append("first")),
        StubRule(r_id=2, rid="failing", callback=fail),
        StubRule(r_id=3, rid="later", callback=lambda: calls.append("later")),
    )

    with pytest.raises(RuntimeError, match="rule exploded"):
        engine({})

    assert calls == ["first", "failing"]
