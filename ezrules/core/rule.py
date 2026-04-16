import ast
from collections.abc import Callable
from typing import Any, NamedTuple

from ezrules.core.application_context import get_user_list_manager
from ezrules.core.rule_helpers import (
    OUTCOME_HELPER_NAME,
    AtNotationConverter,
    BangNotationConverter,
    DollarNotationConverter,
    RuleParamExtractor,
    extract_outcome_helper_value,
)
from ezrules.core.user_lists import AbstractUserListManager
from ezrules.models.backend_core import Rule as RuleModel


class Fields:
    LOGIC = "logic"
    DESCRIPTION = "description"
    PARAMS = "params"
    RID = "rid"
    R_ID = "r_id"


class Rule:
    """Generic rule representation class."""

    def __init__(
        self,
        rid: str,
        logic: str,
        description: str | None = None,
        params: list[str] | None = None,
        r_id: int | None = None,
        list_values_provider: AbstractUserListManager | None = None,
    ) -> None:
        """
        Creates a rule object.

        :param logic: A valid python code
        :param description: Human-readable description of the rule
        :param rid: rule id, can not be changed after the rule is created
        :param params: rule params, not used atm
        """
        # Generic params
        self.r_id = r_id
        self.rid = rid
        self.description = description
        self.params = params
        self._list_values_provider = list_values_provider
        # Compiled rule function
        self._compiled_rule = None
        # AST representation of the compiled function
        self._rule_ast = None
        self._rule_params: set[str] = set()
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
    def compile_function(code: str) -> tuple[Callable, ast.Module]:
        rule_ast = ast.parse(code)
        OutcomeReturnSyntaxValidator().visit(rule_ast)
        compiled_code = compile(rule_ast, filename="<string>", mode="exec")
        namespace = {OUTCOME_HELPER_NAME: lambda outcome: outcome}
        exec(compiled_code, namespace)
        return namespace["rule"], rule_ast

    @logic.setter
    def logic(self, logic):
        """Compile the code."""
        # Build a fresh converter per compilation to avoid shared parser state
        # across concurrent API requests.
        post_proc_logic = DollarNotationConverter().transform_rule(logic)
        post_proc_logic = BangNotationConverter().transform_rule(post_proc_logic)
        # Get the list provider from application context
        list_provider = self._list_values_provider or get_user_list_manager()
        at_converter = AtNotationConverter(list_values_provider=list_provider)
        post_proc_logic = at_converter.transform_rule(post_proc_logic)
        code = self._wrap_with_function_header(post_proc_logic)
        self._compiled_rule, self._rule_ast = self.compile_function(code)
        self._source = logic
        self._post_process_logic = code
        self._rule_params = self._extract_rule_params()

    def _extract_rule_params(self) -> set[str]:
        pe = RuleParamExtractor()
        pe.visit(self._rule_ast)
        return pe.params

    def get_rule_params(self):
        return set(self._rule_params)

    def __call__(self, t) -> Any:
        """Executes rule logic."""
        try:
            return self.logic(t)
        except KeyError as exc:
            missing_field = exc.args[0] if exc.args else None
            if isinstance(missing_field, str) and missing_field in self._rule_params:
                raise MissingFieldLookupError(
                    field_name=missing_field,
                    rule_identifier=self.rid or self.r_id,
                ) from exc
            raise

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
    def from_json(rule_config, list_values_provider: AbstractUserListManager | None = None) -> Rule:
        rule = Rule(
            logic=rule_config[Fields.LOGIC],
            description=rule_config.get(Fields.DESCRIPTION),
            rid=rule_config.get(Fields.RID),
            params=rule_config.get(Fields.PARAMS, ()),
            r_id=rule_config.get(Fields.R_ID),
            list_values_provider=list_values_provider,
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
            Fields.R_ID: rule.r_id,
        }


class StoredRule(NamedTuple):
    rule: Rule
    rule_model: RuleModel


class MissingFieldLookupError(Exception):
    """Raised when strict rule lookup references a field absent from the event."""

    def __init__(self, field_name: str, rule_identifier: str | int | None):
        self.field_name = field_name
        self.rule_identifier = rule_identifier
        if rule_identifier is None or rule_identifier == "":
            message = f"Rule lookup failed: field '{field_name}' is missing from the event"
        else:
            message = f"Rule '{rule_identifier}' lookup failed: field '{field_name}' is missing from the event"
        super().__init__(message)


class OutcomeReturnSyntaxError(SyntaxError):
    """Raised when a rule returns an outcome without direct !OUTCOME syntax."""

    def __init__(self, outcome_name: str, line: int, column: int, end_column: int):
        self.outcome_name = outcome_name
        self.lineno = line
        self.offset = column
        self.end_lineno = line
        self.end_offset = end_column
        if outcome_name:
            message = f"Use return !{outcome_name} instead of indirect or quoted outcome returns."
        else:
            message = "Outcome returns must use direct `return !OUTCOME` syntax."
        super().__init__(message)


class OutcomeReturnSyntaxValidator(ast.NodeVisitor):
    _NOT_STRING = object()
    _UNKNOWN_STRING = object()

    def __init__(self) -> None:
        self._string_like_bindings: list[dict[str, object]] = []

    @property
    def _current_bindings(self) -> dict[str, object]:
        return self._string_like_bindings[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._string_like_bindings.append({})
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._string_like_bindings.pop()
        return node

    def visit_Assign(self, node: ast.Assign) -> Any:
        inferred_value = self._infer_string_like_value(node.value)
        for target in node.targets:
            self._track_assignment(target, inferred_value)
        self.generic_visit(node)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        if node.value is not None:
            inferred_value = self._infer_string_like_value(node.value)
            self._track_assignment(node.target, inferred_value)
        self.generic_visit(node)
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        self._track_assignment(node.target, self._NOT_STRING)
        self.generic_visit(node)
        return node

    def visit_Return(self, node: ast.Return) -> Any:
        if node.value is None:
            return node

        if extract_outcome_helper_value(node.value) is not None:
            return node

        if (
            self._contains_outcome_helper_call(node.value)
            or self._infer_string_like_value(node.value) is not self._NOT_STRING
        ):
            raise OutcomeReturnSyntaxError(
                outcome_name=self._guess_outcome_name(node.value),
                line=node.value.lineno,
                column=node.value.col_offset + 1,
                end_column=node.value.end_col_offset or (node.value.col_offset + 1),
            )

        self.generic_visit(node)
        return node

    def _track_assignment(self, target: ast.AST, inferred_value: object) -> None:
        if not self._string_like_bindings:
            return
        if isinstance(target, ast.Name):
            if inferred_value is self._NOT_STRING:
                self._current_bindings.pop(target.id, None)
            else:
                self._current_bindings[target.id] = inferred_value
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for child_target in target.elts:
                self._track_assignment(child_target, inferred_value)

    def _contains_outcome_helper_call(self, node: ast.AST) -> bool:
        return any(extract_outcome_helper_value(candidate) is not None for candidate in ast.walk(node))

    def _infer_string_like_value(self, node: ast.AST) -> object:
        outcome_value = extract_outcome_helper_value(node)
        if outcome_value is not None:
            return outcome_value

        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return node.value
            return self._NOT_STRING

        if isinstance(node, ast.JoinedStr):
            return self._UNKNOWN_STRING

        if isinstance(node, ast.Name):
            return self._current_bindings.get(node.id, self._NOT_STRING)

        if isinstance(node, ast.IfExp):
            body_value = self._infer_string_like_value(node.body)
            orelse_value = self._infer_string_like_value(node.orelse)
            if body_value is self._NOT_STRING and orelse_value is self._NOT_STRING:
                return self._NOT_STRING
            if (
                body_value is not self._NOT_STRING
                and orelse_value is not self._NOT_STRING
                and body_value == orelse_value
            ):
                return body_value
            return self._UNKNOWN_STRING

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left_value = self._infer_string_like_value(node.left)
            right_value = self._infer_string_like_value(node.right)
            if left_value is self._NOT_STRING and right_value is self._NOT_STRING:
                return self._NOT_STRING
            return self._UNKNOWN_STRING

        return self._NOT_STRING

    def _guess_outcome_name(self, node: ast.AST) -> str:
        inferred_value = self._infer_string_like_value(node)
        return inferred_value if isinstance(inferred_value, str) else ""
