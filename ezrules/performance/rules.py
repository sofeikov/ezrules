from __future__ import annotations

from ezrules.demo_data import DemoRuleDefinition, build_demo_rules

RULE_COMPLEXITY_DEMO_SCALAR_AND_NESTED = "demo_scalar_and_nested"
RULE_COMPLEXITY_SIMPLE = "simple"
SUPPORTED_RULE_COMPLEXITIES = {
    RULE_COMPLEXITY_DEMO_SCALAR_AND_NESTED,
    RULE_COMPLEXITY_SIMPLE,
}


def build_performance_rules(
    *,
    rule_count: int,
    rule_complexity: str,
    start_index: int = 0,
) -> list[DemoRuleDefinition]:
    """Build deterministic rules for one performance matrix complexity."""

    if rule_complexity == RULE_COMPLEXITY_DEMO_SCALAR_AND_NESTED:
        return build_demo_rules(n_rules=rule_count, start_index=start_index)
    if rule_complexity == RULE_COMPLEXITY_SIMPLE:
        return _build_simple_rules(rule_count=rule_count, start_index=start_index)
    raise ValueError(f"Unknown rule complexity: {rule_complexity}")


def _build_simple_rules(*, rule_count: int, start_index: int = 0) -> list[DemoRuleDefinition]:
    rules: list[DemoRuleDefinition] = []
    for offset in range(rule_count):
        absolute_index = start_index + offset + 1
        threshold = 100 + (offset % 20) * 25
        rules.append(
            DemoRuleDefinition(
                rid=f"TestRule_SimpleAmount_{absolute_index:03d}",
                logic=f"if $amount > {threshold}:\n    return !REVIEW\nreturn None",
                description=f"Simple scalar amount threshold {threshold}",
            )
        )
    return rules
