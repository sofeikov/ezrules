import json

from ezrules.backend.ai_rule_authoring import (
    RuleAuthoringProvider,
    RuleDraftCandidate,
    RuleLineExplanation,
    build_rule_authoring_context,
    generate_rule_draft,
)
from ezrules.models.backend_core import (
    AllowedOutcome,
    FieldObservation,
    FieldTypeConfig,
    Organisation,
    UserList,
    UserListEntry,
)


class StubRuleAuthoringProvider(RuleAuthoringProvider):
    provider_name = "openai"
    model_name = "test-model"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        _ = user_prompt
        response = self._responses[self.calls]
        self.calls += 1
        return response


def _json_response(draft_logic: str, explanations: list[tuple[int, str, str]] | None = None) -> str:
    return json.dumps(
        {
            "draft_logic": draft_logic,
            "line_explanations": [
                {"line_number": line_number, "source": source, "explanation": explanation}
                for line_number, source, explanation in (explanations or [])
            ],
        }
    )


def _seed_authoring_context(session) -> None:
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    session.add_all(
        [
            AllowedOutcome(outcome_name="HOLD", severity_rank=10, o_id=int(org.o_id)),
            AllowedOutcome(outcome_name="RELEASE", severity_rank=20, o_id=int(org.o_id)),
            FieldObservation(field_name="amount", observed_json_type="float", o_id=int(org.o_id)),
            FieldObservation(field_name="customer.age_days", observed_json_type="integer", o_id=int(org.o_id)),
            FieldTypeConfig(field_name="amount", configured_type="float", required=True, o_id=int(org.o_id)),
            UserList(list_name="HighRiskCountries", o_id=int(org.o_id)),
        ]
    )
    session.commit()
    user_list = session.query(UserList).filter(UserList.list_name == "HighRiskCountries").one()
    session.add_all(
        [
            UserListEntry(entry_value="IR", ul_id=int(user_list.ul_id)),
            UserListEntry(entry_value="KP", ul_id=int(user_list.ul_id)),
        ]
    )
    session.commit()


def test_build_rule_authoring_context_collects_compact_org_context(session):
    _seed_authoring_context(session)

    context = build_rule_authoring_context(
        session,
        1,
        mode="edit",
        evaluation_lane="main",
        current_logic="if $amount > 100:\n\treturn !HOLD",
        current_description="Existing rule",
        neutral_outcome="RELEASE",
    )

    assert context.mode == "edit"
    assert context.evaluation_lane == "main"
    assert context.current_logic == "if $amount > 100:\n\treturn !HOLD"
    assert context.current_description == "Existing rule"
    assert [field.name for field in context.fields] == ["amount", "customer.age_days"]
    amount_field = next(field for field in context.fields if field.name == "amount")
    assert amount_field.observed_json_types == ["float"]
    assert amount_field.configured_type == "float"
    assert amount_field.required is True
    assert context.user_lists == [type(context.user_lists[0])(name="HighRiskCountries", entry_count=2)]
    assert [outcome.name for outcome in context.outcomes] == ["HOLD", "RELEASE"]


def test_generate_rule_draft_repairs_invalid_model_output(session, monkeypatch):
    _seed_authoring_context(session)
    provider = StubRuleAuthoringProvider(
        [
            _json_response("if $amount > 100:\n\treturn !UNKNOWN"),
            _json_response(
                "if $amount > 100:\n\treturn !HOLD",
                [(1, "if $amount > 100:", "Checks the high amount condition.")],
            ),
        ]
    )
    monkeypatch.setattr("ezrules.backend.ai_rule_authoring.get_rule_authoring_provider", lambda db, org_id: provider)

    result = generate_rule_draft(
        session,
        1,
        prompt="Flag high value transfers.",
        mode="create",
        evaluation_lane="main",
        current_logic=None,
        current_description=None,
    )

    assert provider.calls == 2
    assert result.applyable is True
    assert result.repair_attempted is True
    assert result.validation.valid is True
    assert result.validation.errors == []
    assert result.draft_logic == "if $amount > 100:\n\treturn !HOLD"
    assert result.line_explanations[0].line_number == 1
    assert result.line_explanations[1].source == "\treturn !HOLD"


def test_generate_rule_draft_enforces_allowlist_lane_constraints(session, monkeypatch):
    _seed_authoring_context(session)
    provider = StubRuleAuthoringProvider(
        [
            _json_response("if $amount > 100:\n\treturn !HOLD"),
            _json_response(
                "if $amount > 100:\n\treturn !RELEASE",
                [
                    (1, "if $amount > 100:", "Checks the amount threshold."),
                    (2, "\treturn !RELEASE", "Returns the neutral outcome for allowlist matches."),
                ],
            ),
        ]
    )
    monkeypatch.setattr("ezrules.backend.ai_rule_authoring.get_rule_authoring_provider", lambda db, org_id: provider)

    result = generate_rule_draft(
        session,
        1,
        prompt="Allowlist known low risk transfers.",
        mode="create",
        evaluation_lane="allowlist",
        current_logic=None,
        current_description=None,
    )

    assert provider.calls == 2
    assert result.applyable is True
    assert result.repair_attempted is True
    assert result.validation.valid is True
    assert result.draft_logic.endswith("return !RELEASE")


def test_generate_rule_draft_returns_invalid_result_after_exhausting_repairs(session, monkeypatch):
    _seed_authoring_context(session)
    provider = StubRuleAuthoringProvider(
        [
            "not json",
            _json_response("if $amount > 100:\n\treturn !UNKNOWN"),
            _json_response("if $amount > 100:\n\treturn !UNKNOWN"),
        ]
    )
    monkeypatch.setattr("ezrules.backend.ai_rule_authoring.get_rule_authoring_provider", lambda db, org_id: provider)

    result = generate_rule_draft(
        session,
        1,
        prompt="Flag a risky transfer.",
        mode="create",
        evaluation_lane="main",
        current_logic=None,
        current_description=None,
    )

    assert provider.calls == 3
    assert result.applyable is False
    assert result.repair_attempted is True
    assert result.validation.valid is False
    assert result.validation.errors
