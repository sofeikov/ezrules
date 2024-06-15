from ezrules.core.rule import Rule, RuleFactory
from typing import Any, List, Dict
from collections import Counter


class ResultAggregation:
    """Class contains possible values for the result aggregation strategy."""

    UNIQUE = "unique"
    COUNTER = "counter"


class RuleEngine:
    """Main class for executing a set of :class:`core.rule.Rule` objects. It
    is defined as a set of rules and the way the results are aggregated. The ways the results are
    aggregated are specified by :class:`core.rule_engine.ResultAggregation`."""

    def __init__(
        self,
        rules: List[Rule],
        result_aggregation: str = ResultAggregation.UNIQUE,
    ) -> None:
        """

        :param rules: list of :class:`core.rule.Rule`
        :param result_aggregation: a member of :class:`core.rule_engine.ResultAggregation`
        """
        self.rules = rules
        self.result_aggregation = result_aggregation

    def __call__(self, t: Dict) -> Any:
        """
        Execute the rules and aggregated the results.

        :param t: a dictionary containing the attributes rules would rely upon. At this time, no additional validation \
        is done, and it is up to user to pass an appropriately filled in dictionary. In future versions, additional \
        checks will be in place.
        :return: aggregated results, either as a list of unique decisions, or a counter for each decision.
        """
        results = [r(t) for r in self.rules]
        if self.result_aggregation == ResultAggregation.UNIQUE:
            return sorted(list(set(results)))
        elif self.result_aggregation == ResultAggregation.COUNTER:
            return dict(Counter(results).items())
        else:
            raise ValueError(f"Unknown aggregation type: {self.result_aggregation}")


class RuleEngineFactory:
    @staticmethod
    def from_json(config) -> RuleEngine:
        rules = [RuleFactory.from_json(rc) for rc in config]
        rule_engine = RuleEngine(rules=rules)
        return rule_engine
