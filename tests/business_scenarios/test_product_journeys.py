import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    Organisation,
    Role,
    RuleHistory,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel


BUSINESS_OUTCOMES = ("CANCEL", "HOLD", "REVIEW", "RELEASE")


@pytest.fixture(autouse=True)
def reset_evaluator_executors():
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None
    yield
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None


def _seed_business_outcomes(session, *, org_id: int) -> None:
    session.query(AllowedOutcome).filter(AllowedOutcome.o_id == org_id).delete(synchronize_session=False)
    for severity_rank, outcome_name in enumerate(BUSINESS_OUTCOMES, start=1):
        session.add(AllowedOutcome(outcome_name=outcome_name, severity_rank=severity_rank, o_id=org_id))
    session.commit()


def _token_with_permissions(session, *, email: str, permissions: list[PermissionAction]) -> str:
    org = session.query(Organisation).one()
    role = Role(name=f"journey_role_{email}", description="Product journey role", o_id=int(org.o_id))
    user = User(
        email=email,
        password=bcrypt.hashpw("journeypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        active=True,
        fs_uniquifier=email,
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)

    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(user.o_id),
    )


def _manager_token(session, *, email: str = "journey-manager@example.com") -> str:
    return _token_with_permissions(
        session,
        email=email,
        permissions=[
            PermissionAction.VIEW_RULES,
            PermissionAction.CREATE_RULE,
            PermissionAction.MODIFY_RULE,
            PermissionAction.PROMOTE_RULES,
            PermissionAction.PAUSE_RULES,
            PermissionAction.DELETE_RULE,
            PermissionAction.SUBMIT_TEST_EVENTS,
        ],
    )


def _create_rule(client: TestClient, token: str, *, rid: str, logic: str, description: str) -> int:
    response = client.post(
        "/api/v2/rules",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rid": rid,
            "description": description,
            "logic": logic,
            "evaluation_lane": "main",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["rule"]["status"] == "draft"
    return int(payload["rule"]["r_id"])


def _promote_rule(client: TestClient, token: str, rule_id: int) -> None:
    response = client.post(f"/api/v2/rules/{rule_id}/promote", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["rule"]["status"] == "active"


def _evaluate(client: TestClient, api_key: str, *, transaction_id: str, event_data: dict) -> dict:
    response = client.post(
        "/api/v2/evaluate",
        headers={"X-API-Key": api_key},
        json={
            "transaction_id": transaction_id,
            "effective_at": 1710000000,
            "event_data": event_data,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_rule_authoring_to_served_decision_product_journey(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session)
    transaction_id = "journey-author-promote-evaluate"

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_AMOUNT_REVIEW",
            description="Review high-value product journey events",
            logic="if $amount >= 1000:\n\treturn !REVIEW",
        )
        _promote_rule(client, token, rule_id)

        dry_run = client.post(
            "/api/v2/event-tests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "transaction_id": "journey-dry-run",
                "effective_at": 1710000000,
                "event_data": {"amount": 1500, "country": "GB"},
            },
        )
        assert dry_run.status_code == 200
        dry_run_payload = dry_run.json()
        assert dry_run_payload["dry_run"] is True
        assert dry_run_payload["resolved_outcome"] == "REVIEW"
        assert dry_run_payload["event_version"] is None
        assert dry_run_payload["evaluation_id"] is None
        assert session.query(EventVersion).filter(EventVersion.transaction_id == "journey-dry-run").count() == 0

        served = _evaluate(
            client,
            live_api_key,
            transaction_id=transaction_id,
            event_data={"amount": 1500, "country": "GB"},
        )
        assert served["resolved_outcome"] == "REVIEW"
        assert served["rule_results"] == {str(rule_id): "REVIEW"}

        tested_events = client.get(
            "/api/v2/tested-events?limit=200&include_referenced_fields=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert tested_events.status_code == 200
        served_event = next(
            event for event in tested_events.json()["events"] if event["transaction_id"] == transaction_id
        )
        assert served_event["resolved_outcome"] == "REVIEW"
        assert served_event["event_data"] == {"amount": 1500, "country": "GB"}
        assert served_event["triggered_rules"] == [
            {
                "r_id": rule_id,
                "rid": "JOURNEY_AMOUNT_REVIEW",
                "description": "Review high-value product journey events",
                "outcome": "REVIEW",
                "referenced_fields": ["amount"],
            }
        ]

        history = client.get(f"/api/v2/rules/{rule_id}/history", headers={"Authorization": f"Bearer {token}"})
        assert history.status_code == 200
        assert history.json()["history"][-1]["status"] == "active"

    decision = session.query(EvaluationDecision).filter(EvaluationDecision.transaction_id == transaction_id).one()
    assert decision.resolved_outcome == "REVIEW"
    assert decision.outcome_counters == {"REVIEW": 1}
    stored_results = session.query(EvaluationRuleResult).filter(EvaluationRuleResult.ed_id == decision.ed_id).all()
    assert [(int(result.r_id), str(result.rule_result)) for result in stored_results] == [(rule_id, "REVIEW")]
    rule_history = session.query(RuleHistory).filter(RuleHistory.r_id == rule_id).one()
    assert rule_history.action == "promoted"
    assert rule_history.changed_by == "journey-manager@example.com"


def test_pause_resume_rule_lifecycle_changes_live_serving(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-lifecycle@example.com")

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_DEVICE_HOLD",
            description="Hold low-trust device journey events",
            logic="if $device_trust_score <= 20:\n\treturn !HOLD",
        )
        _promote_rule(client, token, rule_id)

        active_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-lifecycle-active",
            event_data={"device_trust_score": 5},
        )
        assert active_result["resolved_outcome"] == "HOLD"
        assert active_result["rule_results"] == {str(rule_id): "HOLD"}

        pause = client.post(f"/api/v2/rules/{rule_id}/pause", headers={"Authorization": f"Bearer {token}"})
        assert pause.status_code == 200
        assert pause.json()["rule"]["status"] == "paused"

        paused_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-lifecycle-paused",
            event_data={"device_trust_score": 5},
        )
        assert paused_result["resolved_outcome"] is None
        assert paused_result["outcome_counters"] == {}
        assert paused_result["rule_results"] == {}

        resume = client.post(f"/api/v2/rules/{rule_id}/resume", headers={"Authorization": f"Bearer {token}"})
        assert resume.status_code == 200
        assert resume.json()["rule"]["status"] == "active"

        resumed_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-lifecycle-resumed",
            event_data={"device_trust_score": 5},
        )
        assert resumed_result["resolved_outcome"] == "HOLD"
        assert resumed_result["rule_results"] == {str(rule_id): "HOLD"}

    actions = [
        action
        for (action,) in session.query(RuleHistory.action)
        .filter(RuleHistory.r_id == rule_id)
        .order_by(RuleHistory.changed.asc())
        .all()
    ]
    assert actions == ["promoted", "paused", "resumed"]


def test_negative_product_journeys_leave_no_side_effects(session):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    manager_token = _manager_token(session, email="journey-negative-manager@example.com")
    viewer_token = _token_with_permissions(
        session,
        email="journey-negative-viewer@example.com",
        permissions=[PermissionAction.VIEW_RULES],
    )

    with TestClient(app) as client:
        invalid_allowlist = client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={
                "rid": "JOURNEY_BAD_ALLOWLIST",
                "description": "Invalid allowlist should not persist",
                "logic": "if $customer_id == 'trusted':\n\treturn !HOLD",
                "evaluation_lane": "allowlist",
            },
        )
        assert invalid_allowlist.status_code == 201
        assert invalid_allowlist.json()["success"] is False
        assert (
            session.query(RuleModel)
            .filter(RuleModel.o_id == int(org.o_id), RuleModel.rid == "JOURNEY_BAD_ALLOWLIST")
            .count()
            == 0
        )

        forbidden_create = client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "rid": "JOURNEY_FORBIDDEN_CREATE",
                "description": "Viewer must not create rules",
                "logic": "return !REVIEW",
                "evaluation_lane": "main",
            },
        )
        assert forbidden_create.status_code == 403
        assert (
            session.query(RuleModel)
            .filter(RuleModel.o_id == int(org.o_id), RuleModel.rid == "JOURNEY_FORBIDDEN_CREATE")
            .count()
            == 0
        )

        invalid_key_eval = client.post(
            "/api/v2/evaluate",
            headers={"X-API-Key": "ezrk_invalid"},
            json={
                "transaction_id": "journey-invalid-api-key",
                "effective_at": 1710000000,
                "event_data": {"amount": 1500},
            },
        )
        assert invalid_key_eval.status_code == 401
        assert session.query(EventVersion).filter(EventVersion.transaction_id == "journey-invalid-api-key").count() == 0
        assert (
            session.query(EvaluationDecision)
            .filter(EvaluationDecision.transaction_id == "journey-invalid-api-key")
            .count()
            == 0
        )
