import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.ai_rule_authoring import RuleDraftGenerationResult, RuleLineExplanation
from ezrules.backend.api_v2.schemas.rules import RuleVerifyResponse
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AIRuleAuthoringHistory, Organisation, Role, Rule, User


def _create_client(session, *, permissions: list[PermissionAction], email: str) -> TestClient:
    hashed_password = bcrypt.hashpw("aiauthorpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()

    role = Role(name=f"ai-rule-author-{email}", description="AI rule author role", o_id=int(org.o_id))
    session.add(role)
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)

    user = User(
        email=email,
        password=hashed_password,
        active=True,
        fs_uniquifier=email,
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add(user)
    session.commit()

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(org.o_id),
    )
    client = TestClient(app)
    client.test_data = {"token": token, "session": session, "user": user, "org": org}  # type: ignore[attr-defined]
    return client


def _auth_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.test_data['token']}"}  # type: ignore[index]


def _create_rule(session, *, org_id: int) -> Rule:
    rule = Rule(
        rid="AI_EDIT_RULE",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Existing AI edit rule",
        o_id=org_id,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def test_generate_ai_rule_draft_records_generation_history(session, monkeypatch):
    client = _create_client(
        session,
        permissions=[PermissionAction.CREATE_RULE, PermissionAction.ACCESS_AUDIT_TRAIL],
        email="ai-create@example.com",
    )

    monkeypatch.setattr(
        "ezrules.backend.api_v2.routes.rules.generate_rule_draft",
        lambda db,
        current_org_id,
        prompt,
        mode,
        evaluation_lane,
        current_logic,
        current_description: RuleDraftGenerationResult(
            generation_id="gen-001",
            draft_logic="if $amount > 100:\n\treturn !HOLD",
            line_explanations=[
                RuleLineExplanation(
                    line_number=1,
                    source="if $amount > 100:",
                    explanation="Checks the amount threshold.",
                )
            ],
            validation=RuleVerifyResponse(
                valid=True,
                params=["amount"],
                referenced_lists=[],
                referenced_outcomes=["HOLD"],
                warnings=[],
                errors=[],
            ),
            repair_attempted=False,
            applyable=True,
            provider="openai",
            model="test-model",
            prompt_hash="abc123",
            prompt_excerpt="Flag high value transfers",
        ),
    )

    with client:
        response = client.post(
            "/api/v2/rules/ai/draft",
            headers=_auth_headers(client),
            json={
                "prompt": "Flag high value transfers",
                "mode": "create",
                "evaluation_lane": "main",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_id"] == "gen-001"
    assert payload["applyable"] is True
    history = session.query(AIRuleAuthoringHistory).order_by(AIRuleAuthoringHistory.id.asc()).all()
    assert len(history) == 1
    assert history[0].action == "draft_generated"
    assert history[0].prompt_hash == "abc123"


def test_generate_ai_rule_draft_requires_mode_specific_permission(session):
    client = _create_client(
        session,
        permissions=[PermissionAction.CREATE_RULE],
        email="ai-create-only@example.com",
    )
    rule = _create_rule(session, org_id=1)

    with client:
        response = client.post(
            "/api/v2/rules/ai/draft",
            headers=_auth_headers(client),
            json={
                "prompt": "Tighten the rule",
                "mode": "edit",
                "evaluation_lane": "main",
                "rule_id": int(rule.r_id),
                "current_logic": rule.logic,
                "current_description": rule.description,
            },
        )

    assert response.status_code == 403


def test_apply_ai_rule_draft_records_apply_history(session, monkeypatch):
    client = _create_client(
        session,
        permissions=[PermissionAction.MODIFY_RULE, PermissionAction.ACCESS_AUDIT_TRAIL],
        email="ai-edit@example.com",
    )
    rule = _create_rule(session, org_id=1)

    monkeypatch.setattr(
        "ezrules.backend.api_v2.routes.rules.generate_rule_draft",
        lambda db,
        current_org_id,
        prompt,
        mode,
        evaluation_lane,
        current_logic,
        current_description: RuleDraftGenerationResult(
            generation_id="gen-apply",
            draft_logic="if $amount > 500:\n\treturn !HOLD",
            line_explanations=[],
            validation=RuleVerifyResponse(
                valid=True,
                params=["amount"],
                referenced_lists=[],
                referenced_outcomes=["HOLD"],
                warnings=[],
                errors=[],
            ),
            repair_attempted=False,
            applyable=True,
            provider="openai",
            model="test-model",
            prompt_hash="hash-apply",
            prompt_excerpt="Raise the threshold",
        ),
    )

    with client:
        generate_response = client.post(
            "/api/v2/rules/ai/draft",
            headers=_auth_headers(client),
            json={
                "prompt": "Raise the threshold",
                "mode": "edit",
                "evaluation_lane": "main",
                "rule_id": int(rule.r_id),
                "current_logic": rule.logic,
                "current_description": rule.description,
            },
        )
        assert generate_response.status_code == 200

        apply_response = client.post(
            "/api/v2/rules/ai/apply",
            headers=_auth_headers(client),
            json={"generation_id": "gen-apply", "rule_id": int(rule.r_id)},
        )

    assert apply_response.status_code == 200
    history = session.query(AIRuleAuthoringHistory).order_by(AIRuleAuthoringHistory.id.asc()).all()
    assert [entry.action for entry in history] == ["draft_generated", "draft_applied"]
    assert history[-1].r_id == int(rule.r_id)


def test_ai_rule_authoring_audit_endpoint_filters_to_current_org(session):
    client = _create_client(
        session,
        permissions=[PermissionAction.ACCESS_AUDIT_TRAIL],
        email="ai-audit@example.com",
    )
    other_org = Organisation(name="other-ai-audit-org")
    session.add(other_org)
    session.commit()
    session.refresh(other_org)

    session.add_all(
        [
            AIRuleAuthoringHistory(
                generation_id="org-one",
                action="draft_generated",
                mode="create",
                evaluation_lane="main",
                provider="openai",
                model="test-model",
                prompt_excerpt="Org one prompt",
                prompt_hash="org-one-hash",
                validation_status="valid",
                repair_attempted=False,
                applyable=True,
                o_id=1,
                changed_by="ai-audit@example.com",
            ),
            AIRuleAuthoringHistory(
                generation_id="org-two",
                action="draft_generated",
                mode="create",
                evaluation_lane="main",
                provider="openai",
                model="test-model",
                prompt_excerpt="Org two prompt",
                prompt_hash="org-two-hash",
                validation_status="valid",
                repair_attempted=False,
                applyable=True,
                o_id=int(other_org.o_id),
                changed_by="other@example.com",
            ),
        ]
    )
    session.commit()

    with client:
        summary_response = client.get("/api/v2/audit", headers=_auth_headers(client))
        history_response = client.get("/api/v2/audit/ai-rule-authoring", headers=_auth_headers(client))

    assert summary_response.status_code == 200
    assert summary_response.json()["total_ai_rule_authoring_actions"] == 1
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["generation_id"] == "org-one"
