import ast
import json
from typing import Any

import pyparsing as pp

from ezrules.core.user_lists import AbstractUserListManager

OUTCOME_HELPER_NAME = "__ezrules_outcome__"
FIELD_LOOKUP_HELPER_NAME = "__ezrules_lookup__"


class RuleParamExtractor(ast.NodeVisitor):
    def __init__(self):
        self.params = set()

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        path = self._extract_subscript_path(node)
        if path is not None:
            self.params.add(path)
            return node
        return super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if self._is_compiler_field_lookup_call(node):
            field_arg = node.args[1]
            assert isinstance(field_arg, ast.Constant) and isinstance(field_arg.value, str)
            self.params.add(field_arg.value)
            return node
        return super().generic_visit(node)

    def _is_compiler_field_lookup_call(self, node: ast.Call) -> bool:
        """Return True only for the canonical helper call emitted by `$field.path`.

        Downstream field analysis is used by verify warnings, test JSON prefill,
        and backtesting missing-field eligibility checks. If we accepted broader
        helper shapes here, hand-written calls or computed arguments could
        masquerade as canonical `$...` references and bypass those guardrails.
        """
        return (
            isinstance(node.func, ast.Name)
            and node.func.id == FIELD_LOOKUP_HELPER_NAME
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "t"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        )

    def _extract_subscript_path(self, node: ast.Subscript) -> str | None:
        segments: list[str] = []
        current: ast.AST = node

        while isinstance(current, ast.Subscript):
            if not isinstance(current.slice, ast.Constant) or not isinstance(current.slice.value, str):
                return None
            segments.append(current.slice.value)
            current = current.value

        if isinstance(current, ast.Name) and current.id == "t":
            return ".".join(reversed(segments))
        return None


class TriggerReferenceExtractor:
    def __init__(self, trigger_char: str):
        search_for_word = pp.Combine(pp.Literal(trigger_char) + pp.Word(pp.alphas + "_", pp.alphanums + "_"))
        line_parser = search_for_word
        line_parser.ignore(pp.QuotedString('"'))
        line_parser.ignore(pp.QuotedString("'"))
        line_parser.ignore(pp.pythonStyleComment)
        self._parser = line_parser

    def extract(self, code: str) -> list[str]:
        references: list[str] = []

        def collect_reference(tokens):
            references.append(tokens[0][1:])
            return tokens[0]

        parser = self._parser.copy()
        parser.setParseAction(collect_reference)
        parser.transform_string(code)
        return references


class DollarNotationConverter:
    TRIGGER_CHAR = "$"

    def replace_with_matched_text(self, tokens):
        return f"{FIELD_LOOKUP_HELPER_NAME}(t, {json.dumps(tokens[0][1:])})"

    def __init__(self):
        identifier = pp.Word(pp.alphas + "_", pp.alphanums + "_")
        if self.TRIGGER_CHAR == "$":
            search_for_word = pp.Combine(self.TRIGGER_CHAR + identifier + pp.ZeroOrMore(pp.Literal(".") + identifier))
        else:
            search_for_word = pp.Combine(self.TRIGGER_CHAR + identifier)

        line_parser = search_for_word
        line_parser.ignore(pp.QuotedString('"'))
        line_parser.ignore(pp.QuotedString("'"))
        line_parser.ignore(pp.pythonStyleComment)
        line_parser.setParseAction(self.replace_with_matched_text)
        self._parser = line_parser

    def transform_rule(self, code: str):
        return self._parser.transform_string(code)


class BangNotationConverter(DollarNotationConverter):
    TRIGGER_CHAR = "!"

    def replace_with_matched_text(self, tokens):
        return f"{OUTCOME_HELPER_NAME}({json.dumps(tokens[0][1:].upper())})"


class AtNotationConverter(DollarNotationConverter):
    TRIGGER_CHAR = "@"

    def __init__(self, list_values_provider: AbstractUserListManager):
        super().__init__()
        self.list_values_provider = list_values_provider

    def replace_with_matched_text(self, tokens):
        return json.dumps(self.list_values_provider.get_entries(tokens[0][1:]))


class UserListReferenceExtractor(TriggerReferenceExtractor):
    def __init__(self):
        super().__init__("@")


class OutcomeReferenceExtractor(TriggerReferenceExtractor):
    def __init__(self):
        super().__init__("!")


def extract_outcome_helper_value(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if node.keywords or len(node.args) != 1:
        return None
    if not isinstance(node.func, ast.Name) or node.func.id != OUTCOME_HELPER_NAME:
        return None
    argument = node.args[0]
    if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
        return None
    return argument.value
