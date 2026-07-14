from collections import Counter
from typing import Any, TypedDict

from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import AbstractUserListManager

RULE_EXECUTION_MODE_ALL_MATCHES = "all_matches"
RULE_EXECUTION_MODE_FIRST_MATCH = "first_match"
RULE_EXECUTION_MODES = frozenset(
    {
        RULE_EXECUTION_MODE_ALL_MATCHES,
        RULE_EXECUTION_MODE_FIRST_MATCH,
    }
)

RuleIdentifier = int | str


class RuleEngineResult(TypedDict):
    rule_results: dict[RuleIdentifier, str]
    all_rule_results: dict[RuleIdentifier, str | None]
    outcome_counters: dict[str, int]
    outcome_set: list[str]


class InvalidRuleResultError(TypeError):
    """Raised when a rule returns a value that cannot represent an outcome."""


def validate_rule_result(rule_identifier: RuleIdentifier, rule_result: Any) -> str | None:
    """Return a valid outcome result or reject values that cannot be aggregated."""
    if rule_result is None:
        return None
    if not isinstance(rule_result, str):
        raise InvalidRuleResultError(
            f"Rule {rule_identifier!r} returned {type(rule_result).__name__}; "
            "expected None or a non-empty outcome string"
        )
    if not rule_result:
        raise InvalidRuleResultError(
            f"Rule {rule_identifier!r} returned an empty outcome string; expected None or a non-empty outcome string"
        )
    return rule_result


class RuleEngine:
    """Main class for executing a set of :class:`core.rule.Rule` objects. It
    is defined as a set of rules and the way the results are aggregated. The ways the results are
    aggregated are specified by :class:`core.rule_engine.ResultAggregation`."""

    def __init__(
        self,
        rules: list[Rule],
        execution_mode: str = RULE_EXECUTION_MODE_ALL_MATCHES,
    ) -> None:
        """

        :param rules: list of :class:`core.rule.Rule`
        :param result_aggregation: a member of :class:`core.rule_engine.ResultAggregation`
        """
        if execution_mode not in RULE_EXECUTION_MODES:
            raise ValueError(f"Unknown rule execution mode: {execution_mode!r}")

        seen_identifiers: set[RuleIdentifier] = set()
        for rule in rules:
            identifier = self._rule_identifier(rule)
            if identifier in seen_identifiers:
                raise ValueError(f"Duplicate rule identifier: {identifier!r}")
            seen_identifiers.add(identifier)

        self.rules = rules
        self.execution_mode = execution_mode

    @staticmethod
    def _rule_identifier(rule: Rule) -> RuleIdentifier:
        return rule.r_id if rule.r_id is not None else rule.rid

    def get_rule_stats(self) -> set[str]:
        stat_paths: set[str] = set()
        for rule in self.rules:
            stat_paths.update(rule.get_rule_stats())
        return stat_paths

    def __call__(self, t: dict, stats: dict[str, Any] | None = None) -> RuleEngineResult:
        """
        Execute the rules and aggregated the results.

        :param t: a dictionary containing the attributes rules would rely upon. At this time, no additional validation \
        is done, and it is up to user to pass an appropriately filled in dictionary. In future versions, additional \
        checks will be in place.
        :return: aggregated results, either as a list of unique decisions, or a counter for each decision.
        """
        all_rule_results: dict[RuleIdentifier, str | None] = {}
        for rule in self.rules:
            rule_id = self._rule_identifier(rule)
            rule_result = validate_rule_result(rule_id, rule(t, stats=stats))
            all_rule_results[rule_id] = rule_result
            if self.execution_mode == RULE_EXECUTION_MODE_FIRST_MATCH and rule_result is not None:
                break
        rule_results = {r: res for r, res in all_rule_results.items() if res is not None}
        outcome_counters = dict(Counter(rule_results.values()))
        outcome_set = sorted(set(outcome_counters.keys()))
        results: RuleEngineResult = {
            "rule_results": rule_results,
            "all_rule_results": all_rule_results,
            "outcome_counters": outcome_counters,
            "outcome_set": outcome_set,
        }
        return results


class RuleEngineFactory:
    @staticmethod
    def from_json(
        config,
        list_values_provider: AbstractUserListManager | None = None,
        execution_mode: str = RULE_EXECUTION_MODE_ALL_MATCHES,
    ) -> RuleEngine:
        rules = [RuleFactory.from_json(rc, list_values_provider=list_values_provider) for rc in config]
        rule_engine = RuleEngine(rules=rules, execution_mode=execution_mode)
        return rule_engine
