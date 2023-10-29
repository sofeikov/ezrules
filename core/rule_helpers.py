import ast
import pyparsing as pp
from typing import Any


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
    @staticmethod
    def replace_with_matched_text(tokens):
        return f'f["{tokens[0][1:]}"]'

    def __init__(self):
        dollar_word = pp.Combine("$" + pp.Word(pp.alphas + "_", pp.alphanums + "_"))

        line_parser = dollar_word
        line_parser.ignore(pp.QuotedString('"'))
        line_parser.setParseAction(self.replace_with_matched_text)
        self._parser = line_parser

    def transform_rule(self, code: str):
        return self._parser.transform_string(code)
