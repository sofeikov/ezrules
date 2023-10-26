import ast
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
