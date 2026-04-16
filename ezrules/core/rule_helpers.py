import ast
import json
from typing import Any

import pyparsing as pp

from ezrules.core.user_lists import AbstractUserListManager

OUTCOME_HELPER_NAME = "__ezrules_outcome__"


class RuleParamExtractor(ast.NodeVisitor):
    def __init__(self):
        self.params = set()

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        super().generic_visit(node)
        if isinstance(node.value, ast.Name):
            if node.value.id == "t" and isinstance(node.slice, ast.Constant):
                self.params.add(node.slice.value)
        return node


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
        return f't["{tokens[0][1:]}"]'

    def __init__(self):
        search_for_word = pp.Combine(self.TRIGGER_CHAR + pp.Word(pp.alphas + "_", pp.alphanums + "_"))

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
