from ezrules.core.rule import Rule
from ezrules.core.rule_engine import (
    RULE_EXECUTION_MODE_ALL_MATCHES,
    RULE_EXECUTION_MODE_FIRST_MATCH,
    RuleEngine,
)


def test_rule_engine_all_matches_keeps_existing_behavior():
    rules = [Rule(logic='return "HOLD"', rid="rule-1", r_id=1), Rule(logic='return "RELEASE"', rid="rule-2", r_id=2)]

    result = RuleEngine(rules=rules, execution_mode=RULE_EXECUTION_MODE_ALL_MATCHES)({"amount": 10})

    assert result["outcome_counters"] == {"HOLD": 1, "RELEASE": 1}
    assert result["outcome_set"] == ["HOLD", "RELEASE"]
    assert result["rule_results"] == {1: "HOLD", 2: "RELEASE"}
    assert result["all_rule_results"] == {1: "HOLD", 2: "RELEASE"}


def test_rule_engine_first_match_stops_after_first_hit():
    rules = [Rule(logic='return "HOLD"', rid="rule-1", r_id=1), Rule(logic='return "RELEASE"', rid="rule-2", r_id=2)]

    result = RuleEngine(rules=rules, execution_mode=RULE_EXECUTION_MODE_FIRST_MATCH)({"amount": 10})

    assert result["outcome_counters"] == {"HOLD": 1}
    assert result["outcome_set"] == ["HOLD"]
    assert result["rule_results"] == {1: "HOLD"}
    assert result["all_rule_results"] == {1: "HOLD"}
