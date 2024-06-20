from ezrules.core.rule import Rule
from ezrules.core.rule_engine import RuleEngine


def test_can_run_simple_rule():
    rules = [Rule(logic='return "HOLD"', rid=1), Rule(logic='return "CANCEL"', rid=2)]
    re = RuleEngine(rules=rules)
    result = re({"A": 1})
    assert result["outcome_counters"] == {"HOLD": 1, "CANCEL": 1}
    assert result["outcome_set"] == ["CANCEL", "HOLD"]
    assert result["rule_results"] == {1: "HOLD", 2: "CANCEL"}
