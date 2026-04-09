from collections import Counter
from typing import Any

from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import AbstractUserListManager

RULE_EXECUTION_MODE_ALL_MATCHES = "all_matches"
RULE_EXECUTION_MODE_FIRST_MATCH = "first_match"


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
        self.rules = rules
        self.execution_mode = execution_mode

    def __call__(self, t: dict) -> Any:
        """
        Execute the rules and aggregated the results.

        :param t: a dictionary containing the attributes rules would rely upon. At this time, no additional validation \
        is done, and it is up to user to pass an appropriately filled in dictionary. In future versions, additional \
        checks will be in place.
        :return: aggregated results, either as a list of unique decisions, or a counter for each decision.
        """
        all_rule_results: dict[Any, Any] = {}
        for rule in self.rules:
            rule_id = rule.r_id or rule.rid
            rule_result = rule(t)
            all_rule_results[rule_id] = rule_result
            if self.execution_mode == RULE_EXECUTION_MODE_FIRST_MATCH and rule_result is not None:
                break
        rule_results = {r: res for r, res in all_rule_results.items() if res is not None}
        outcome_counters = dict(Counter(rule_results.values()))
        outcome_set = sorted(set(outcome_counters.keys()))
        results = {
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
