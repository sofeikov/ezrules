import abc
import ast
from typing import Any

from ezrules.core.outcomes import Outcome
from ezrules.core.rule import Rule


class RuleChecker:
    @abc.abstractmethod
    def check_rule(self, rule: Rule) -> tuple[bool, str]:
        """Check if a rule is valid."""


class AllowedOutcomeReturnVisitor(ast.NodeVisitor):
    def __init__(self):
        self.values = []

    def visit_Return(self, node) -> Any:
        if isinstance(node.value, ast.Constant):
            self.values.append(node.value.value)
        else:
            self.values.append(None)


class OnlyAllowedOutcomesAreReturnedChecker(RuleChecker):
    def __init__(self, outcome_manager: Outcome) -> None:
        self.outcome_manager = outcome_manager

    def check_rule(self, rule: Rule) -> tuple[bool, list[str]]:
        v = AllowedOutcomeReturnVisitor()
        v.visit(rule._rule_ast)
        returned_values = v.values
        reasons = []
        for v in returned_values:
            if self.outcome_manager.is_allowed_outcome(v) is False:
                reasons.append(f"Value {v} is not allowed in rule outcome;")
        are_allowed = [self.outcome_manager.is_allowed_outcome(v) for v in returned_values]

        return all(are_allowed), reasons


class RuleCheckingPipeline:
    def __init__(self, checkers: list[RuleChecker]):
        self.checkers = checkers

    def is_rule_valid(self, rule: Rule):
        all_reasons = []
        rule_ok = True
        for c in self.checkers:
            c_allowed, c_reasons = c.check_rule(rule)
            if c_allowed is False:
                rule_ok = False
                all_reasons.extend(c_reasons)

        return rule_ok, all_reasons
