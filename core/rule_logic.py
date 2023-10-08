import ast


class DollarLookupTransformer(ast.NodeTransformer):
    """
    This class is a custom NodeTransformer for the abstract syntax tree (AST) that
    performs a specific transformation on AST nodes of type 'Compare'.

    Attributes:
        None

    Methods:
        visit_Compare(self, node)
    """

    @staticmethod
    def is_dollar_string_comparator(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("$"):
                return True
        return False

    def visit_Compare(self, node):
        """
        Visit and potentially transform a 'Compare' AST node.

        Args:
            node (ast.Compare): The 'Compare' AST node to be visited.

        Returns:
            ast.Compare: The modified or unmodified 'Compare' AST node.
        """
        if DollarLookupTransformer.is_dollar_string_comparator(node.left):
            left_value = node.left.value
            node.left = ast.Subscript(
                value=ast.Name(id="t", ctx=ast.Load()),
                slice=ast.Constant(value=left_value[1:]),
                ctx=ast.Load(),
            )
        if len(
            node.comparators
        ) == 1 and DollarLookupTransformer.is_dollar_string_comparator(
            node.comparators[0]
        ):
            right_value = node.comparators[0].value
            node.comparators = [
                ast.Subscript(
                    value=ast.Name(id="t", ctx=ast.Load()),
                    slice=ast.Constant(value=right_value[1:]),
                    ctx=ast.Load(),
                )
            ]

        return node
