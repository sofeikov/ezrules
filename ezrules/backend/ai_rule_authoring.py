from __future__ import annotations

import hashlib
import json
import textwrap
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func

from ezrules.backend.api_v2.schemas.rules import RuleVerifyError, RuleVerifyResponse
from ezrules.backend.rule_validation import validate_rule_source
from ezrules.backend.runtime_settings import (
    get_ai_authoring_api_key,
    get_ai_authoring_enabled,
    get_ai_authoring_model,
    get_ai_authoring_provider,
)
from ezrules.core.rule_updater import RULE_EVALUATION_LANE_ALLOWLIST
from ezrules.models.backend_core import AllowedOutcome, FieldObservation, FieldTypeConfig, UserList, UserListEntry
from ezrules.settings import app_settings


class AIRuleAuthoringUnavailableError(RuntimeError):
    """Raised when AI authoring is not configured for the backend."""


class AIRuleAuthoringProviderError(RuntimeError):
    """Raised when the configured provider fails to return a usable response."""


@dataclass(frozen=True)
class RuleAuthoringFieldContext:
    name: str
    observed_json_types: list[str]
    configured_type: str | None
    required: bool
    datetime_format: str | None


@dataclass(frozen=True)
class RuleAuthoringListContext:
    name: str
    entry_count: int


@dataclass(frozen=True)
class RuleAuthoringOutcomeContext:
    name: str
    severity_rank: int


@dataclass(frozen=True)
class RuleAuthoringContext:
    mode: str
    evaluation_lane: str
    neutral_outcome: str
    fields: list[RuleAuthoringFieldContext]
    user_lists: list[RuleAuthoringListContext]
    outcomes: list[RuleAuthoringOutcomeContext]
    current_logic: str | None
    current_description: str | None


@dataclass(frozen=True)
class RuleLineExplanation:
    line_number: int
    source: str
    explanation: str


@dataclass(frozen=True)
class RuleDraftCandidate:
    draft_logic: str
    line_explanations: list[RuleLineExplanation]


@dataclass(frozen=True)
class RuleDraftGenerationResult:
    generation_id: str
    draft_logic: str
    line_explanations: list[RuleLineExplanation]
    validation: RuleVerifyResponse
    repair_attempted: bool
    applyable: bool
    provider: str
    model: str
    prompt_hash: str
    prompt_excerpt: str


class RuleAuthoringProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...


class OpenAIRuleAuthoringProvider:
    provider_name = "openai"

    def __init__(self, *, base_url: str, model_name: str, api_key: str | None, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - exercised via tests with monkeypatches
            details = exc.read().decode("utf-8", errors="ignore")
            raise AIRuleAuthoringProviderError(
                f"AI authoring provider returned HTTP {exc.code}: {details[:300] or 'no response body'}"
            ) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - exercised via tests with monkeypatches
            raise AIRuleAuthoringProviderError(f"AI authoring provider request failed: {exc.reason!s}") from exc

        try:
            choice = response_payload["choices"][0]
            message = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIRuleAuthoringProviderError("AI authoring provider returned an unexpected response shape.") from exc

        if isinstance(message, list):
            parts: list[str] = []
            for item in message:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            message = "\n".join(part for part in parts if part.strip())

        if not isinstance(message, str) or not message.strip():
            raise AIRuleAuthoringProviderError("AI authoring provider returned an empty completion.")

        return message


def get_rule_authoring_provider(db: Any, org_id: int) -> RuleAuthoringProvider:
    provider_name = get_ai_authoring_provider(db, org_id)
    enabled = get_ai_authoring_enabled(db, org_id)
    model_name = get_ai_authoring_model(db, org_id)
    api_key = get_ai_authoring_api_key(db, org_id)

    if not enabled:
        raise AIRuleAuthoringUnavailableError("AI rule authoring is disabled in Settings.")
    if provider_name != "openai":
        raise AIRuleAuthoringUnavailableError(
            "AI rule authoring is configured with an unsupported provider. "
            "OpenAI is the only supported provider right now."
        )
    if not model_name:
        raise AIRuleAuthoringUnavailableError("AI rule authoring is not configured. Set an OpenAI model in Settings.")
    if not api_key.strip():
        raise AIRuleAuthoringUnavailableError("AI rule authoring is not configured. Add an OpenAI API key in Settings.")

    return OpenAIRuleAuthoringProvider(
        base_url=app_settings.AI_AUTHORING_BASE_URL,
        model_name=model_name,
        api_key=api_key,
        timeout_seconds=app_settings.AI_AUTHORING_TIMEOUT_SECONDS,
    )


def build_rule_authoring_context(
    db: Any,
    org_id: int,
    *,
    mode: str,
    evaluation_lane: str,
    current_logic: str | None,
    current_description: str | None,
    neutral_outcome: str,
) -> RuleAuthoringContext:
    field_configs = {
        str(config.field_name): config
        for config in db.query(FieldTypeConfig).filter(FieldTypeConfig.o_id == org_id).all()
    }

    observed_types: dict[str, set[str]] = {}
    for field_name, observed_json_type in (
        db.query(FieldObservation.field_name, FieldObservation.observed_json_type)
        .filter(FieldObservation.o_id == org_id)
        .order_by(FieldObservation.field_name.asc(), FieldObservation.observed_json_type.asc())
        .all()
    ):
        observed_types.setdefault(str(field_name), set()).add(str(observed_json_type))

    field_names = sorted(set(observed_types) | set(field_configs))
    fields = [
        RuleAuthoringFieldContext(
            name=field_name,
            observed_json_types=sorted(observed_types.get(field_name, set())),
            configured_type=str(field_configs[field_name].configured_type) if field_name in field_configs else None,
            required=bool(field_configs[field_name].required) if field_name in field_configs else False,
            datetime_format=str(field_configs[field_name].datetime_format)
            if field_name in field_configs and field_configs[field_name].datetime_format is not None
            else None,
        )
        for field_name in field_names
    ]

    list_rows = (
        db.query(UserList.list_name, func.count(UserListEntry.ule_id))
        .outerjoin(UserListEntry, UserListEntry.ul_id == UserList.ul_id)
        .filter(UserList.o_id == org_id)
        .group_by(UserList.ul_id, UserList.list_name)
        .order_by(UserList.list_name.asc())
        .all()
    )
    user_lists = [
        RuleAuthoringListContext(name=str(list_name), entry_count=int(entry_count or 0))
        for list_name, entry_count in list_rows
    ]

    outcomes = [
        RuleAuthoringOutcomeContext(name=str(outcome.outcome_name), severity_rank=int(outcome.severity_rank))
        for outcome in (
            db.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == org_id)
            .order_by(AllowedOutcome.severity_rank.asc(), AllowedOutcome.outcome_name.asc())
            .all()
        )
    ]

    return RuleAuthoringContext(
        mode=mode,
        evaluation_lane=evaluation_lane,
        neutral_outcome=neutral_outcome,
        fields=fields,
        user_lists=user_lists,
        outcomes=outcomes,
        current_logic=(current_logic or "").strip() or None,
        current_description=(current_description or "").strip() or None,
    )


def _summarize_lane_constraint(evaluation_lane: str, neutral_outcome: str) -> str:
    if evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST:
        return (
            f"This is an allowlist rule. It must contain at least one return !{neutral_outcome} statement "
            f"and may only return !{neutral_outcome}."
        )
    return (
        "This is a main rule. It may return any configured outcome and participates in the normal outcome "
        "resolution flow."
    )


def _build_generation_system_prompt() -> str:
    return textwrap.dedent(
        """
        You write ezrules rule bodies from analyst requests.

        Return a JSON object with exactly these keys:
        - draft_logic: string
        - line_explanations: array of objects with line_number, source, explanation

        Constraints:
        - draft_logic must be only the rule body, not a full function, not markdown, and no code fences.
        - Use ezrules notation exactly: $field.path, @UserListName, !OUTCOME.
        - Prefer only fields, lists, and outcomes provided in context.
        - Keep logic concise and valid Python-style rule code using if/elif/else and return statements.
        - line_explanations must explain each non-empty line of draft_logic in order.
        """
    ).strip()


def _build_generation_user_prompt(prompt: str, context: RuleAuthoringContext) -> str:
    prompt_payload = {
        "analyst_request": prompt,
        "mode": context.mode,
        "evaluation_lane": context.evaluation_lane,
        "lane_constraint": _summarize_lane_constraint(context.evaluation_lane, context.neutral_outcome),
        "neutral_outcome": context.neutral_outcome,
        "available_outcomes": [
            {"name": outcome.name, "severity_rank": outcome.severity_rank} for outcome in context.outcomes
        ],
        "available_user_lists": [
            {"name": user_list.name, "entry_count": user_list.entry_count} for user_list in context.user_lists
        ],
        "available_fields": [
            {
                "name": field.name,
                "observed_json_types": field.observed_json_types,
                "configured_type": field.configured_type,
                "required": field.required,
                "datetime_format": field.datetime_format,
            }
            for field in context.fields
        ],
        "current_rule_context": {
            "description": context.current_description,
            "logic": context.current_logic,
        },
    }
    return json.dumps(prompt_payload, indent=2, sort_keys=True)


def _build_repair_user_prompt(
    prompt: str,
    context: RuleAuthoringContext,
    *,
    previous_output: str,
    current_draft: str | None,
    issues: list[str],
) -> str:
    prompt_payload = {
        "analyst_request": prompt,
        "mode": context.mode,
        "evaluation_lane": context.evaluation_lane,
        "lane_constraint": _summarize_lane_constraint(context.evaluation_lane, context.neutral_outcome),
        "previous_model_output": previous_output,
        "current_draft_logic": current_draft,
        "issues_to_fix": issues,
        "neutral_outcome": context.neutral_outcome,
        "available_outcomes": [outcome.name for outcome in context.outcomes],
        "available_user_lists": [user_list.name for user_list in context.user_lists],
        "available_fields": [field.name for field in context.fields],
    }
    return json.dumps(prompt_payload, indent=2, sort_keys=True)


def _extract_json_block(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            stripped = "\n".join(lines[1:-1]).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return stripped
    return stripped[start : end + 1]


def _parse_candidate(raw_text: str) -> tuple[RuleDraftCandidate | None, str | None]:
    try:
        payload = json.loads(_extract_json_block(raw_text))
    except json.JSONDecodeError as exc:
        return None, f"Model response was not valid JSON: {exc.msg}"

    if not isinstance(payload, dict):
        return None, "Model response must be a JSON object."

    draft_logic = payload.get("draft_logic")
    if not isinstance(draft_logic, str) or not draft_logic.strip():
        return None, "Model response must include a non-empty draft_logic string."

    explanations_payload = payload.get("line_explanations")
    raw_explanations = explanations_payload if isinstance(explanations_payload, list) else []
    explanations: list[RuleLineExplanation] = []
    for item in raw_explanations:
        if not isinstance(item, dict):
            continue
        line_number = item.get("line_number")
        source = item.get("source")
        explanation = item.get("explanation")
        if not isinstance(line_number, int) or not isinstance(source, str) or not isinstance(explanation, str):
            continue
        if not explanation.strip():
            continue
        explanations.append(
            RuleLineExplanation(
                line_number=line_number,
                source=source,
                explanation=explanation.strip(),
            )
        )

    return RuleDraftCandidate(draft_logic=draft_logic.strip(), line_explanations=explanations), None


def _fallback_line_explanation(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("if "):
        return "Checks whether the branch condition matches the incoming event."
    if stripped.startswith("elif "):
        return "Checks the next candidate condition when earlier branches did not match."
    if stripped == "else:":
        return "Handles the fallback branch when earlier conditions do not match."
    if stripped.startswith("return !"):
        return "Returns the configured outcome when the active branch matches."
    if stripped.startswith("return "):
        return "Returns the computed result for the active branch."
    return "Executes this part of the draft rule logic."


def _normalize_line_explanations(candidate: RuleDraftCandidate) -> list[RuleLineExplanation]:
    candidate_by_line = {explanation.line_number: explanation for explanation in candidate.line_explanations}
    candidate_by_source = {
        explanation.source.strip(): explanation
        for explanation in candidate.line_explanations
        if explanation.source.strip()
    }
    normalized: list[RuleLineExplanation] = []
    for line_number, source in enumerate(candidate.draft_logic.splitlines(), start=1):
        if not source.strip():
            continue
        preferred = candidate_by_line.get(line_number)
        if preferred is None:
            preferred = candidate_by_source.get(source.strip())
        explanation_text = preferred.explanation if preferred is not None else _fallback_line_explanation(source)
        normalized.append(
            RuleLineExplanation(
                line_number=line_number,
                source=source,
                explanation=explanation_text,
            )
        )
    return normalized


def _build_invalid_validation(error_messages: list[str]) -> RuleVerifyResponse:
    return RuleVerifyResponse(
        valid=False,
        params=[],
        referenced_lists=[],
        referenced_outcomes=[],
        warnings=[],
        errors=[
            RuleVerifyError(
                message=message,
                line=None,
                column=None,
                end_line=None,
                end_column=None,
            )
            for message in error_messages
        ],
    )


def _prompt_excerpt(prompt: str, *, max_length: int = 240) -> str:
    normalized = " ".join(prompt.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def generate_rule_draft(
    db: Any,
    org_id: int,
    *,
    prompt: str,
    mode: str,
    evaluation_lane: str,
    current_logic: str | None,
    current_description: str | None,
) -> RuleDraftGenerationResult:
    provider = get_rule_authoring_provider(db, org_id)
    neutral_outcome = "RELEASE"
    if evaluation_lane == RULE_EVALUATION_LANE_ALLOWLIST:
        from ezrules.backend.runtime_settings import get_neutral_outcome  # local import avoids cycle pressure

        neutral_outcome = get_neutral_outcome(db, org_id)

    context = build_rule_authoring_context(
        db,
        org_id,
        mode=mode,
        evaluation_lane=evaluation_lane,
        current_logic=current_logic,
        current_description=current_description,
        neutral_outcome=neutral_outcome,
    )
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    prompt_excerpt = _prompt_excerpt(prompt)

    system_prompt = _build_generation_system_prompt()
    last_output = provider.complete(
        system_prompt=system_prompt,
        user_prompt=_build_generation_user_prompt(prompt, context),
    )

    repair_attempted = False
    candidate: RuleDraftCandidate | None = None
    validation = _build_invalid_validation(["AI authoring did not return a draft."])

    for attempt in range(3):
        candidate, parse_error = _parse_candidate(last_output)
        issues: list[str] = []
        if parse_error is not None:
            issues = [parse_error]
            validation = _build_invalid_validation(issues)
        else:
            assert candidate is not None
            validation = validate_rule_source(
                db,
                org_id,
                candidate.draft_logic,
                evaluation_lane=evaluation_lane,
                description=current_description or "",
            ).response
            if validation.valid and not validation.errors:
                return RuleDraftGenerationResult(
                    generation_id=str(uuid.uuid4()),
                    draft_logic=candidate.draft_logic,
                    line_explanations=_normalize_line_explanations(candidate),
                    validation=validation,
                    repair_attempted=repair_attempted,
                    applyable=True,
                    provider=provider.provider_name,
                    model=provider.model_name,
                    prompt_hash=prompt_hash,
                    prompt_excerpt=prompt_excerpt,
                )
            issues = [error.message for error in validation.errors]

        if attempt == 2:
            break

        repair_attempted = True
        last_output = provider.complete(
            system_prompt=system_prompt,
            user_prompt=_build_repair_user_prompt(
                prompt,
                context,
                previous_output=last_output,
                current_draft=candidate.draft_logic if candidate is not None else None,
                issues=issues,
            ),
        )

    return RuleDraftGenerationResult(
        generation_id=str(uuid.uuid4()),
        draft_logic=candidate.draft_logic if candidate is not None else "",
        line_explanations=_normalize_line_explanations(candidate) if candidate is not None else [],
        validation=validation,
        repair_attempted=repair_attempted,
        applyable=False,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_hash=prompt_hash,
        prompt_excerpt=prompt_excerpt,
    )
