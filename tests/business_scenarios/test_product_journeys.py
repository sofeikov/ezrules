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
    EventVersionLabel,
    Label,
    Organisation,
    Role,
    RuleDeploymentResultsLog,
    RuleHistory,
    RuleQualityPair,
    User,
    UserListEntry,
    UserListHistory,
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
            PermissionAction.MANAGE_BACKTESTS,
            PermissionAction.MANAGE_SHADOW_DEPLOYMENTS,
            PermissionAction.MANAGE_ROLLOUTS,
            PermissionAction.VIEW_LISTS,
            PermissionAction.CREATE_LIST,
            PermissionAction.MODIFY_LIST,
            PermissionAction.DELETE_LIST,
            PermissionAction.VIEW_LABELS,
            PermissionAction.CREATE_LABEL,
            PermissionAction.MODIFY_LABEL,
            PermissionAction.ACCESS_AUDIT_TRAIL,
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


def _get_rule(client: TestClient, token: str, rule_id: int) -> dict:
    response = client.get(f"/api/v2/rules/{rule_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


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


def test_permission_grant_and_revoke_controls_rule_authoring(session):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    email = "journey-permissions@example.com"
    token = _token_with_permissions(
        session,
        email=email,
        permissions=[PermissionAction.VIEW_RULES],
    )
    role = session.query(Role).filter(Role.name == f"journey_role_{email}", Role.o_id == int(org.o_id)).one()

    with TestClient(app) as client:
        forbidden_before_grant = client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "JOURNEY_PERMISSION_BEFORE_GRANT",
                "description": "Role without create permission must not create",
                "logic": "return !REVIEW",
                "evaluation_lane": "main",
            },
        )
        assert forbidden_before_grant.status_code == 403
        assert (
            session.query(RuleModel)
            .filter(RuleModel.o_id == int(org.o_id), RuleModel.rid == "JOURNEY_PERMISSION_BEFORE_GRANT")
            .count()
            == 0
        )

        PermissionManager.db_session = session
        PermissionManager.grant_permission(int(role.id), PermissionAction.CREATE_RULE)

        created_rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_PERMISSION_AFTER_GRANT",
            description="Role can create after create permission grant",
            logic="return !REVIEW",
        )
        assert (
            session.query(RuleModel).filter(RuleModel.o_id == int(org.o_id), RuleModel.r_id == created_rule_id).count()
            == 1
        )

        PermissionManager.revoke_permission(int(role.id), PermissionAction.CREATE_RULE)

        forbidden_after_revoke = client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rid": "JOURNEY_PERMISSION_AFTER_REVOKE",
                "description": "Role must lose create ability after revoke",
                "logic": "return !REVIEW",
                "evaluation_lane": "main",
            },
        )
        assert forbidden_after_revoke.status_code == 403
        assert (
            session.query(RuleModel)
            .filter(RuleModel.o_id == int(org.o_id), RuleModel.rid == "JOURNEY_PERMISSION_AFTER_REVOKE")
            .count()
            == 0
        )


def test_rule_edit_requires_promotion_before_serving_new_logic(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-edit@example.com")

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_EDIT_RULE",
            description="Review high amount before edit",
            logic="if $amount >= 1000:\n\treturn !REVIEW",
        )
        _promote_rule(client, token, rule_id)

        before_edit = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-edit-before",
            event_data={"amount": 1500},
        )
        assert before_edit["resolved_outcome"] == "REVIEW"
        assert before_edit["rule_results"] == {str(rule_id): "REVIEW"}

        update = client.put(
            f"/api/v2/rules/{rule_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "description": "Hold high amount after edit",
                "logic": "if $amount >= 1000:\n\treturn !HOLD",
            },
        )
        assert update.status_code == 200
        assert update.json()["rule"]["status"] == "draft"

        while_draft = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-edit-draft",
            event_data={"amount": 1500},
        )
        assert while_draft["resolved_outcome"] is None
        assert while_draft["rule_results"] == {}

        _promote_rule(client, token, rule_id)

        after_promote = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-edit-after",
            event_data={"amount": 1500},
        )
        assert after_promote["resolved_outcome"] == "HOLD"
        assert after_promote["rule_results"] == {str(rule_id): "HOLD"}

        history = client.get(f"/api/v2/rules/{rule_id}/history", headers={"Authorization": f"Bearer {token}"})
        assert history.status_code == 200
        assert [entry["status"] for entry in history.json()["history"]] == ["draft", "active", "draft", "active"]

    actions = [
        action
        for (action,) in session.query(RuleHistory.action)
        .filter(RuleHistory.r_id == rule_id)
        .order_by(RuleHistory.changed.asc())
        .all()
    ]
    assert actions == ["promoted", "updated", "promoted"]


def test_user_list_mutation_changes_rule_serving_and_audit(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-lists@example.com")

    with TestClient(app) as client:
        list_response = client.post(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "JourneyWatchlistCustomers"},
        )
        assert list_response.status_code == 201
        list_id = int(list_response.json()["list"]["id"])

        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_WATCHLIST_RULE",
            description="Hold watchlisted customers",
            logic="if $customer_id in @JourneyWatchlistCustomers:\n\treturn !HOLD",
        )
        _promote_rule(client, token, rule_id)

        missing_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-list-before-add",
            event_data={"customer_id": "cust_watch_001"},
        )
        assert missing_result["resolved_outcome"] is None
        assert missing_result["rule_results"] == {}

        entry_response = client.post(
            f"/api/v2/user-lists/{list_id}/entries",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "cust_watch_001"},
        )
        assert entry_response.status_code == 201
        entry_id = int(entry_response.json()["entry"]["id"])

        listed_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-list-hit",
            event_data={"customer_id": "cust_watch_001"},
        )
        assert listed_result["resolved_outcome"] == "HOLD"
        assert listed_result["rule_results"] == {str(rule_id): "HOLD"}

        delete_entry = client.delete(
            f"/api/v2/user-lists/{list_id}/entries/{entry_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_entry.status_code == 200
        assert delete_entry.json()["success"] is True

        removed_result = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-list-miss",
            event_data={"customer_id": "cust_watch_001"},
        )
        assert removed_result["resolved_outcome"] is None
        assert removed_result["rule_results"] == {}

        audit = client.get(f"/api/v2/audit/user-lists?list_id={list_id}", headers={"Authorization": f"Bearer {token}"})
        assert audit.status_code == 200
        assert [item["action"] for item in audit.json()["items"]] == ["entry_removed", "entry_added", "created"]

    history_actions = [
        action
        for (action,) in session.query(UserListHistory.action)
        .filter(UserListHistory.ul_id == list_id)
        .order_by(UserListHistory.changed.asc())
        .all()
    ]
    assert history_actions == ["created", "entry_added", "entry_removed"]
    remaining_entries = session.query(UserListEntry).filter(UserListEntry.ul_id == list_id).count()
    assert remaining_entries == 0


def test_label_rule_quality_and_audit_journey(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-quality@example.com")

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_QUALITY_RULE",
            description="Hold risky quality events",
            logic="if $risk_score >= 80:\n\treturn !HOLD",
        )
        _promote_rule(client, token, rule_id)

        label_response = client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"label_name": "journey_fraud"},
        )
        assert label_response.status_code == 201
        label_name = label_response.json()["label"]["label"]

        session.add(
            RuleQualityPair(
                outcome="HOLD",
                label=label_name,
                active=True,
                created_by="journey-quality@example.com",
                o_id=int(org.o_id),
            )
        )
        session.commit()

        for index, risk_score in enumerate((95, 88)):
            transaction_id = f"journey-quality-fraud-{index}"
            evaluated = _evaluate(
                client,
                live_api_key,
                transaction_id=transaction_id,
                event_data={"risk_score": risk_score},
            )
            assert evaluated["resolved_outcome"] == "HOLD"
            mark = client.post(
                "/api/v2/labels/mark-event",
                headers={"Authorization": f"Bearer {token}"},
                json={"transaction_id": transaction_id, "label_name": label_name},
            )
            assert mark.status_code == 200
            assert mark.json()["success"] is True

        quality = client.get("/api/v2/analytics/rule-quality", headers={"Authorization": f"Bearer {token}"})
        assert quality.status_code == 200
        quality_payload = quality.json()
        assert quality_payload["total_labeled_events"] == 2
        metric = next(
            item
            for item in quality_payload["pair_metrics"]
            if item["r_id"] == rule_id and item["outcome"] == "HOLD" and item["label"] == label_name
        )
        assert metric["true_positive"] == 2
        assert metric["false_positive"] == 0
        assert metric["false_negative"] == 0
        assert metric["precision"] == pytest.approx(1.0)
        assert metric["recall"] == pytest.approx(1.0)
        assert metric["f1"] == pytest.approx(1.0)

        label_audit = client.get("/api/v2/audit/labels", headers={"Authorization": f"Bearer {token}"})
        assert label_audit.status_code == 200
        assert [item["action"] for item in label_audit.json()["items"][:3]] == ["assigned", "assigned", "created"]

    label = session.query(Label).filter(Label.o_id == int(org.o_id), Label.label == label_name).one()
    labeled_event_count = (
        session.query(EventVersionLabel)
        .filter(EventVersionLabel.o_id == int(org.o_id), EventVersionLabel.el_id == label.el_id)
        .count()
    )
    assert labeled_event_count == 2


def test_rollout_candidate_logs_provenance_without_changing_control_rule(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-rollout@example.com")

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_ROLLOUT_RULE",
            description="Control review rule",
            logic="if $amount >= 1000:\n\treturn !REVIEW",
        )
        _promote_rule(client, token, rule_id)

        deploy = client.post(
            f"/api/v2/rules/{rule_id}/rollout",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "logic": "if $amount >= 1000:\n\treturn !HOLD",
                "description": "Candidate hold rule",
                "traffic_percent": 100,
            },
        )
        assert deploy.status_code == 200
        assert deploy.json()["success"] is True

        served = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-rollout-served",
            event_data={"amount": 1500},
        )
        assert served["resolved_outcome"] == "HOLD"
        assert served["rule_results"] == {str(rule_id): "HOLD"}

        current_rule = _get_rule(client, token, rule_id)
        assert current_rule["logic"] == "if $amount >= 1000:\n\treturn !REVIEW"

    log = (
        session.query(RuleDeploymentResultsLog)
        .filter(
            RuleDeploymentResultsLog.ed_id == int(served["evaluation_id"]), RuleDeploymentResultsLog.r_id == rule_id
        )
        .one()
    )
    assert log.mode == "split"
    assert log.selected_variant == "candidate"
    assert log.traffic_percent == 100
    assert log.control_result == "REVIEW"
    assert log.candidate_result == "HOLD"
    assert log.returned_result == "HOLD"
