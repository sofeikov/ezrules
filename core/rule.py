from typing import Any, Optional, List, Callable, Tuple
from core.rule_helpers import RuleParamExtractor, DollarNotationConverter
import ast
import yaml

dollar_converter = DollarNotationConverter()


class Fields:
    LOGIC = "logic"
    TAGS = "tags"
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
        tags: Optional[List[str]] = None,
        params: Optional[List[str]] = None,
    ) -> None:
        """
        Creates a rule object.

        :param logic: A valid python code
        :param description: Human-readable description of the rule
        :param rid: rule id, can not be changed after the rule is created
        :param tags: rule tags, not used atm
        :param params: rule params, not used atm
        """
        # Generic params
        self.rid = rid
        self.description = description
        self.tags = tags
        self.params = params
        # Compiled rule function
        self._compiled_rule = None
        # AST representation of the compiled function
        self._rule_ast = None
        # Trigger the rule compilation
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
        logic = dollar_converter.transform_rule(logic)
        code = self._wrap_with_function_header(logic)
        self._compiled_rule, self._rule_ast = self.compile_function(code)
        self._source = logic

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
                f"Tags: {self.tags}",
                f"Params: {self.params}",
                "Code:",
                self._source,
            ]
        )


class RuleFactory:
    @staticmethod
    def from_json(rule_config) -> Rule:
        rule = Rule(
            logic=rule_config[Fields.LOGIC],
            description=rule_config.get(Fields.DESCRIPTION),
            rid=rule_config.get(Fields.RID),
            tags=rule_config.get(Fields.TAGS, tuple()),
            params=rule_config.get(Fields.PARAMS, tuple()),
        )
        return rule


class RuleConverter:
    @staticmethod
    def to_json(rule: Rule):
        return {
            Fields.RID: rule.rid,
            Fields.DESCRIPTION: rule.description,
            Fields.TAGS: rule.tags,
            Fields.LOGIC: rule._source,
            Fields.PARAMS: rule.params,
        }


if __name__ == "__main__":
    with open("rule-config.yaml", "r") as f:
        config = yaml.safe_load(f)
        rule_config = config["Rules"][0]

        rule = RuleFactory.from_json(rule_config)

        t = {"send_country": "US", "score": 950}
        print(rule(t))
