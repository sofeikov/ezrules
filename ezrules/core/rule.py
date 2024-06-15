from typing import Any, Optional, List, Callable, Tuple
from ezrules.core.rule_helpers import (
    RuleParamExtractor,
    DollarNotationConverter,
    AtNotationConverter,
)
from ezrules.core.user_lists import StaticUserListManager
import ast
import yaml

dollar_converter = DollarNotationConverter()
at_converter = AtNotationConverter(list_values_provider=StaticUserListManager())


class Fields:
    LOGIC = "logic"
    DESCRIPTION = "description"
    PARAMS = "params"
    RID = "rid"


class Rule:
    """Generic rule representation class."""

    def __init__(
        self,
        rid: str,
        logic: str,
        description: Optional[str] = None,
        params: Optional[List[str]] = None
    ) -> None:
        """
        Creates a rule object.

        :param logic: A valid python code
        :param description: Human-readable description of the rule
        :param rid: rule id, can not be changed after the rule is created
        :param params: rule params, not used atm
        """
        # Generic params
        self.rid = rid
        self.description = description
        self.params = params
        # Compiled rule function
        self._compiled_rule = None
        # AST representation of the compiled function
        self._rule_ast = None
        # Trigger the rule compilation
        self._post_process_logic = None
        self.logic = logic
        self._source = logic

    @property
    def logic(self):
        """Property."""
        return self._compiled_rule

    @staticmethod
    def _wrap_with_function_header(logic: str) -> str:
        code = logic.split("\n")
        code = "\n".join(["\t" + line for line in code])
        code = f"def rule(t):\n{code}"
        return code

    @staticmethod
    def compile_function(code: str) -> Tuple[Callable, ast.Module]:
        rule_ast = ast.parse(code)
        compiled_code = compile(rule_ast, filename="<string>", mode="exec")
        namespace = {}
        exec(compiled_code, namespace)
        return namespace["rule"], rule_ast

    @logic.setter
    def logic(self, logic):
        """Compile the code."""
        post_proc_logic = dollar_converter.transform_rule(logic)
        post_proc_logic = at_converter.transform_rule(post_proc_logic)
        code = self._wrap_with_function_header(post_proc_logic)
        self._compiled_rule, self._rule_ast = self.compile_function(code)
        self._source = logic
        self._post_process_logic = code

    def get_rule_params(self):
        pe = RuleParamExtractor()
        pe.visit(self._rule_ast)
        return pe.params

    def __call__(self, t) -> Any:
        """Executes rule logic."""
        return self.logic(t)

    def __repr__(self) -> str:
        """Print rule in a human readable format."""
        return "\n".join(
            [
                f"Name: {self.rid}",
                f"Description: {self.description}",
                f"Params: {self.params}",
                "Code:",
                self._source,
                "Processed code:",
                str(self._post_process_logic),
            ]
        )


class RuleFactory:
    @staticmethod
    def from_json(rule_config) -> Rule:
        rule = Rule(
            logic=rule_config[Fields.LOGIC],
            description=rule_config.get(Fields.DESCRIPTION),
            rid=rule_config.get(Fields.RID),
            params=rule_config.get(Fields.PARAMS, tuple()),
        )
        return rule


class RuleConverter:
    @staticmethod
    def to_json(rule: Rule):
        return {
            Fields.RID: rule.rid,
            Fields.DESCRIPTION: rule.description,
            Fields.LOGIC: rule._source,
            Fields.PARAMS: rule.params,
        }