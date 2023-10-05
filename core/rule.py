from typing import Any, Optional, List
from core.rule_logic import DollarLookupTransformer
import ast
import yaml


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
        logic: str,
        description: Optional[str] = None,
        rid: Optional[str] = None,
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
        self._logic = None
        self.description = description
        self.logic = logic
        self._source = logic
        self.rid = rid
        self.tags = tags
        self.params = params

    @property
    def logic(self):
        """Property."""
        return self._logic

    @logic.setter
    def logic(self, logic):
        """Compile the code."""
        code = logic.split("\n")
        code = "\n".join(["\t" + l for l in code])
        code = f"def rule(t):\n{code}"
        rule_ast = ast.parse(code)
        DollarLookupTransformer().visit(rule_ast)
        ast.fix_missing_locations(rule_ast)
        compiled_code = compile(rule_ast, filename="<string>", mode="exec")
        namespace = {}
        exec(compiled_code, namespace)
        self._logic = namespace["rule"]
        self._source = logic

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
