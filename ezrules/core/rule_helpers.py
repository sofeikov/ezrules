import ast
import json
import pyparsing as pp
from typing import Any
from ezrules.core.user_lists import AbstractUserListManager


class RuleParamExtractor(ast.NodeVisitor):
    def __init__(self):
        self.params = set()

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        super().generic_visit(node)
        if isinstance(node.value, ast.Name):
            if node.value.id == "t" and isinstance(node.slice, ast.Constant):
                self.params.add(node.slice.value)
        return node


class DollarNotationConverter:
    TRIGGER_CHAR = "$"

    def replace_with_matched_text(self, tokens):
        return f't["{tokens[0][1:]}"]'

    def __init__(self):
        search_for_word = pp.Combine(
            self.TRIGGER_CHAR + pp.Word(pp.alphas + "_", pp.alphanums + "_")
        )

        line_parser = search_for_word
        line_parser.ignore(pp.QuotedString('"'))
        line_parser.setParseAction(self.replace_with_matched_text)
        self._parser = line_parser

    def transform_rule(self, code: str):
        return self._parser.transform_string(code)


class AtNotationConverter(DollarNotationConverter):
    TRIGGER_CHAR = "@"

    def __init__(self, list_values_provider: AbstractUserListManager):
        super().__init__()
        self.list_values_provider = list_values_provider

    def replace_with_matched_text(self, tokens):
        return json.dumps(self.list_values_provider.get_entries(tokens[0][1:]))
