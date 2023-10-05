import ast
import pytest

from core.rule_logic import (
    DollarLookupTransformer,
)


@pytest.mark.parametrize(
    "input_code, expected_code",
    [
        (
            """
if "$var1" == "$var2":
    x = 42
            """,
            """
if t['var1'] == t['var2']:
    x = 42
            """,
        ),
        (
            """
if "$var1" == 37:
    x = 42
            """,
            """
if t['var1'] == 37:
    x = 42
            """,
        ),
        (
            """
if 37 == 37:
    x = 42
            """,
            """
if 37 == 37:
    x = 42
        """,
        ),
        (
            """
if 37 == "$yolo":
    x = 42
            """,
            """
if 37 == t['yolo']:
    x = 42
        """,
        ),
    ],
)
def test_dollar_lookup_transformer(input_code, expected_code):
    transformer = DollarLookupTransformer()
    tree = ast.parse(input_code)
    transformed_tree = transformer.visit(tree)
    unparsed_code = ast.unparse(transformed_tree)
    expected_code = ast.unparse(ast.parse(expected_code))
    assert unparsed_code == expected_code
