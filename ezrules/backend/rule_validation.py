from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ezrules.backend.api_v2.schemas.rules import RuleVerifyError, RuleVerifyResponse
from ezrules.backend.runtime_settings import get_neutral_outcome
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.rule import OutcomeReturnSyntaxError, Rule
from ezrules.core.rule_checkers import AllowedOutcomeReturnVisitor
from ezrules.core.rule_helpers import OutcomeReferenceExtractor, UserListReferenceExtractor
from ezrules.core.rule_updater import RULE_EVALUATION_LANE_ALLOWLIST, RULE_EVALUATION_LANE_MAIN
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import FieldObservation


@dataclass(frozen=True)
class RuleValidationResult:
    compiled_rule: Rule | None
    response: RuleVerifyResponse


def get_list_provider(db: Any, org_id: int) -> PersistentUserListManager:
    return PersistentUserListManager(db_session=db, o_id=org_id)


def get_outcome_manager(db: Any, org_id: int) -> DatabaseOutcome:
    return DatabaseOutcome(db_session=db, o_id=org_id)


def build_rule_warnings(db: Any, org_id: int, referenced_fields: list[str]) -> list[str]:
    if not referenced_fields:
        return []

    observed_fields = {
        str(field_name)
        for (field_name,) in db.query(FieldObservation.field_name)
        .filter(FieldObservation.o_id == org_id, FieldObservation.field_name.in_(referenced_fields))
        .distinct()
        .all()
    }
    unseen_fields = [field_name for field_name in referenced_fields if field_name not in observed_fields]
    return [
        (
            f"Field '{field_name}' has not been observed in traffic or test payloads yet. "
            "Backtests will skip historical events where it is missing or null."
        )
        for field_name in unseen_fields
    ]


def unique_preserving_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def extract_referenced_lists(rule_source: str) -> list[str]:
    return unique_preserving_order(UserListReferenceExtractor().extract(rule_source))


def extract_referenced_outcomes(rule_source: str) -> list[str]:
    return [outcome.upper() for outcome in unique_preserving_order(OutcomeReferenceExtractor().extract(rule_source))]


def find_reference_bounds(rule_source: str, reference: str) -> tuple[int, int, int, int] | None:
    for line_number, line_text in enumerate(rule_source.splitlines(), start=1):
        start = line_text.find(reference)
        if start == -1:
            continue
        column = start + 1
        end_column = column + len(reference)
        return (line_number, column, line_number, end_column)
    return None


def build_verify_error(
    message: str,
    line: int | None = None,
    column: int | None = None,
    end_line: int | None = None,
    end_column: int | None = None,
) -> RuleVerifyError:
    return RuleVerifyError(
        message=message,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )


def normalize_rule_source_line(line: int | None) -> int | None:
    if line is None:
        return None
    if line <= 1:
        return 1
    return line - 1


def normalize_rule_source_column(column: int | None) -> int | None:
    if column is None:
        return None
    return max(1, column - 1)


def build_outcome_notation_errors(db: Any, org_id: int, rule_source: str) -> list[RuleVerifyError]:
    errors: list[RuleVerifyError] = []
    allowed_outcomes = set(get_outcome_manager(db, org_id).get_allowed_outcomes())

    raw_outcome_references = unique_preserving_order(OutcomeReferenceExtractor().extract(rule_source))
    for raw_outcome_name in raw_outcome_references:
        outcome_name = raw_outcome_name.upper()
        if outcome_name in allowed_outcomes:
            continue
        location = find_reference_bounds(rule_source, f"!{raw_outcome_name}")
        errors.append(
            build_verify_error(
                message=f"Outcome '!{outcome_name}' is not configured in Outcomes.",
                line=location[0] if location else None,
                column=location[1] if location else None,
                end_line=location[2] if location else None,
                end_column=location[3] if location else None,
            )
        )

    return errors


def validate_allowlist_rule(rule: Rule, allowlist_outcome: str) -> str | None:
    visitor = AllowedOutcomeReturnVisitor()
    visitor.visit(rule._rule_ast)
    if not visitor.values:
        return f"Allowlist rules must contain at least one return !{allowlist_outcome} statement."

    invalid_values = [value for value in visitor.values if value != allowlist_outcome]
    if invalid_values:
        rendered_values = ", ".join(sorted({repr(value) for value in invalid_values}))
        return (
            f"Allowlist rules must return only the configured neutral outcome !{allowlist_outcome}. "
            f"Found {rendered_values}."
        )
    return None


def validate_rule_source(
    db: Any,
    org_id: int,
    rule_source: str,
    *,
    evaluation_lane: str = RULE_EVALUATION_LANE_MAIN,
    rid: str = "",
    description: str = "",
) -> RuleValidationResult:
    referenced_lists = extract_referenced_lists(rule_source)
    referenced_outcomes = extract_referenced_outcomes(rule_source)
    outcome_errors = build_outcome_notation_errors(db, org_id, rule_source)
    if outcome_errors:
        return RuleValidationResult(
            compiled_rule=None,
            response=RuleVerifyResponse(
                valid=False,
                params=[],
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=[],
                errors=outcome_errors,
            ),
        )

    try:
        compiled_rule = Rule(
            rid=rid,
            logic=rule_source,
            description=description,
            list_values_provider=get_list_provider(db, org_id),
        )
        params = sorted(compiled_rule.get_rule_params(), key=str)
        warnings = build_rule_warnings(db, org_id, params)
        if evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST:
            allowlist_error = validate_allowlist_rule(compiled_rule, get_neutral_outcome(db, org_id))
            if allowlist_error is not None:
                return RuleValidationResult(
                    compiled_rule=compiled_rule,
                    response=RuleVerifyResponse(
                        valid=False,
                        params=params,
                        referenced_lists=referenced_lists,
                        referenced_outcomes=referenced_outcomes,
                        warnings=warnings,
                        errors=[build_verify_error(message=allowlist_error)],
                    ),
                )

        return RuleValidationResult(
            compiled_rule=compiled_rule,
            response=RuleVerifyResponse(
                valid=True,
                params=params,
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=warnings,
                errors=[],
            ),
        )
    except OutcomeReturnSyntaxError as exc:
        return RuleValidationResult(
            compiled_rule=None,
            response=RuleVerifyResponse(
                valid=False,
                params=[],
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=[],
                errors=[
                    build_verify_error(
                        message=str(exc),
                        line=normalize_rule_source_line(exc.lineno),
                        column=normalize_rule_source_column(exc.offset),
                        end_line=normalize_rule_source_line(exc.end_lineno),
                        end_column=normalize_rule_source_column(exc.end_offset),
                    )
                ],
            ),
        )
    except SyntaxError as exc:
        message = exc.msg or "Rule source is invalid"
        return RuleValidationResult(
            compiled_rule=None,
            response=RuleVerifyResponse(
                valid=False,
                params=[],
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=[],
                errors=[
                    build_verify_error(
                        message=message,
                        line=normalize_rule_source_line(exc.lineno),
                        column=normalize_rule_source_column(exc.offset),
                        end_line=normalize_rule_source_line(exc.end_lineno),
                        end_column=normalize_rule_source_column(exc.end_offset),
                    )
                ],
            ),
        )
    except KeyError as exc:
        message = str(exc.args[0]) if exc.args else "Rule source is invalid"
        missing_list_match = re.search(r"List '([^']+)' not found", message)
        location = None
        if missing_list_match:
            location = find_reference_bounds(rule_source, f"@{missing_list_match.group(1)}")
        return RuleValidationResult(
            compiled_rule=None,
            response=RuleVerifyResponse(
                valid=False,
                params=[],
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=[],
                errors=[
                    build_verify_error(
                        message=message,
                        line=location[0] if location else None,
                        column=location[1] if location else None,
                        end_line=location[2] if location else None,
                        end_column=location[3] if location else None,
                    )
                ],
            ),
        )
    except Exception as exc:
        return RuleValidationResult(
            compiled_rule=None,
            response=RuleVerifyResponse(
                valid=False,
                params=[],
                referenced_lists=referenced_lists,
                referenced_outcomes=referenced_outcomes,
                warnings=[],
                errors=[build_verify_error(message=str(exc) or "Rule source is invalid")],
            ),
        )
