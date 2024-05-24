from core.rule_engine import RuleEngine, ResultAggregation
from core.rule import Rule
import pytest


@pytest.mark.parametrize(
    ["result_aggregation", "expected_result"],
    [
        (ResultAggregation.UNIQUE, ["CANCEL", "HOLD"]),
        (ResultAggregation.COUNTER, {"CANCEL": 1, "HOLD": 1}),
    ],
)
def test_can_run_simple_rule(result_aggregation, expected_result):
    rules = [Rule(logic='return "HOLD"', rid=1), Rule(logic='return "CANCEL"', rid=2)]
    re = RuleEngine(rules=rules, result_aggregation=result_aggregation)
    res = re({"A": 1})
    assert res == expected_result

def test_raises_unknown_aggregation():
    re = RuleEngine(rules=[], result_aggregation="NOPE")
    with pytest.raises(ValueError):
        re({})