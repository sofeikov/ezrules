from datetime import UTC, datetime

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import execute_backtest_rule_change
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    EventVersionLabel,
    FeatureDefinition,
    FeatureSnapshotResolution,
    Label,
    Organisation,
    Role,
    RuleBackTestingResult,
    RuleDeploymentResultsLog,
    RuleHistory,
    RuleQualityPair,
    TransactionCurrentVersion,
    User,
    UserList,
    UserListEntry,
    UserListHistory,
)
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import _hash_payload, add_served_decision

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
        password=bcrypt.hashpw(b"journeypass", bcrypt.gensalt()).decode("utf-8"),
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
            PermissionAction.GENERATE_RULE_QUALITY_REPORTS,
            PermissionAction.SUBMIT_TEST_EVENTS,
            PermissionAction.VIEW_LISTS,
            PermissionAction.CREATE_LIST,
            PermissionAction.MODIFY_LIST,
            PermissionAction.DELETE_LIST,
            PermissionAction.VIEW_LABELS,
            PermissionAction.CREATE_LABEL,
            PermissionAction.VIEW_FEATURES,
            PermissionAction.MODIFY_FEATURES,
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


def _evaluate(
    client: TestClient,
    api_key: str,
    *,
    transaction_id: str,
    event_data: dict,
    effective_at: int | str = 1710000000,
    observed_at: int | str | None = None,
) -> dict:
    payload = {
        "transaction_id": transaction_id,
        "effective_at": effective_at,
        "event_data": event_data,
    }
    if observed_at is not None:
        payload["observed_at"] = observed_at
    response = client.post(
        "/api/v2/evaluate",
        headers={"X-API-Key": api_key},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_active_sum_feature(
    client: TestClient,
    token: str,
    *,
    name: str = "Sender sent amount 24h",
    feature_name: str = "sent_amount_sum_24h",
) -> int:
    response = client.post(
        "/api/v2/features",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "Canonical journey sender velocity feature",
            "entity": "sender",
            "feature_name": feature_name,
            "entity_key": "sender_id",
            "aggregation_type": "sum",
            "source_field": "amount",
            "window_seconds": 86400,
            "filters": [],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    feature_id = int(payload["feature"]["fd_id"])

    activate = client.post(f"/api/v2/features/{feature_id}/activate", headers={"Authorization": f"Bearer {token}"})
    assert activate.status_code == 200
    assert activate.json()["feature"]["status"] == "active"
    return feature_id


def _add_feature_source_event(
    session,
    *,
    org_id: int,
    transaction_id: str,
    effective_at: datetime,
    event_data: dict,
    observed_at: datetime | None = None,
) -> EventVersion:
    latest = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    event = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1 if latest is None else int(latest.event_version) + 1,
        effective_at=effective_at,
        observed_at=observed_at or effective_at,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
        supersedes_ev_id=None if latest is None else int(latest.ev_id),
    )
    session.add(event)
    session.flush()
    return event


def _mark_event_label(client: TestClient, token: str, *, transaction_id: str, label_name: str) -> None:
    mark = client.post(
        "/api/v2/labels/mark-event",
        headers={"Authorization": f"Bearer {token}"},
        json={"transaction_id": transaction_id, "label_name": label_name},
    )
    assert mark.status_code == 200
    assert mark.json()["success"] is True


def _create_label(client: TestClient, token: str, *, label_name: str) -> str:
    response = client.post(
        "/api/v2/labels",
        headers={"Authorization": f"Bearer {token}"},
        json={"label_name": label_name},
    )
    assert response.status_code == 201
    return str(response.json()["label"]["label"])


def test_feature_aware_evaluation_product_journey(session, live_api_key):
    org = session.query(Organisation).one()
    _seed_business_outcomes(session, org_id=int(org.o_id))
    token = _manager_token(session, email="journey-feature@example.com")

    with TestClient(app) as client:
        feature_id = _create_active_sum_feature(client, token)

        _evaluate(
            client,
            live_api_key,
            transaction_id="journey-feature-prior",
            effective_at="2026-05-05T12:00:00Z",
            observed_at="2026-05-05T12:00:10Z",
            event_data={"sender_id": "S1", "amount": 60},
        )
        _evaluate(
            client,
            live_api_key,
            transaction_id="journey-feature-future-noise",
            effective_at="2026-05-06T13:00:00Z",
            observed_at="2026-05-06T13:00:10Z",
            event_data={"sender_id": "S1", "amount": 10_000},
        )

        hold_rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_FEATURE_HOLD",
            description="Hold senders with prior 24h volume",
            logic="if stat[sender.sent_amount_sum_24h] >= 50:\n\treturn !HOLD",
        )
        leak_guard_rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_FEATURE_LEAK_GUARD",
            description="Cancel only if current or future data leaked into the snapshot",
            logic="if stat[sender.sent_amount_sum_24h] >= 100:\n\treturn !CANCEL",
        )
        _promote_rule(client, token, hold_rule_id)
        _promote_rule(client, token, leak_guard_rule_id)
        evaluator_router._lre = None

        served = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-feature-current",
            effective_at="2026-05-05T13:00:00Z",
            event_data={"sender_id": "S1", "amount": 45},
        )
        assert served["resolved_outcome"] == "HOLD"
        assert served["rule_results"] == {str(hold_rule_id): "HOLD"}
        assert str(leak_guard_rule_id) not in served["rule_results"]

        tested_events = client.get(
            "/api/v2/tested-events?limit=200&include_referenced_fields=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert tested_events.status_code == 200
        current_event = next(
            event for event in tested_events.json()["events"] if event["transaction_id"] == "journey-feature-current"
        )
        assert current_event["resolved_outcome"] == "HOLD"
        assert current_event["triggered_rules"][0]["rid"] == "JOURNEY_FEATURE_HOLD"
        assert current_event["triggered_rules"][0]["metadata_source"] == "evaluation_snapshot"

    decision = (
        session.query(EvaluationDecision).filter(EvaluationDecision.transaction_id == "journey-feature-current").one()
    )
    assert decision.resolved_outcome == "HOLD"
    trace = session.query(FeatureSnapshotResolution).filter_by(ed_id=int(decision.ed_id)).one()
    assert int(trace.fd_id) == feature_id
    assert trace.stat_path == "sender.sent_amount_sum_24h"
    assert trace.resolution_status == "resolved"
    assert trace.matched_event_count == 1
    assert trace.as_of.replace(tzinfo=UTC) == datetime(2026, 5, 5, 13, 0, tzinfo=UTC)


def test_historical_correction_product_journey(session, live_api_key):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _seed_business_outcomes(session, org_id=org_id)
    token = _manager_token(session, email="journey-correction@example.com")

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_CORRECTION_HOLD",
            description="Hold the original high amount",
            logic="if $amount >= 100:\n\treturn !HOLD",
        )
        _promote_rule(client, token, rule_id)

        original = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-corrected-transaction",
            effective_at="2026-05-05T12:00:00Z",
            observed_at="2026-05-05T12:01:00Z",
            event_data={"amount": 150, "sender_id": "S1"},
        )
        correction = _evaluate(
            client,
            live_api_key,
            transaction_id="journey-corrected-transaction",
            effective_at="2026-05-05T12:00:00Z",
            observed_at="2026-05-05T12:30:00Z",
            event_data={"amount": 50, "sender_id": "S1"},
        )

    assert original["evaluation_status"] == "new"
    assert correction["evaluation_status"] == "superseding"
    assert original["resolved_outcome"] == "HOLD"
    assert correction["resolved_outcome"] is None

    decisions = (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.transaction_id == "journey-corrected-transaction")
        .order_by(EvaluationDecision.event_version.asc())
        .all()
    )
    assert [bool(decision.is_current) for decision in decisions] == [False, True]
    assert int(decisions[0].superseded_by_ed_id) == int(decisions[1].ed_id)

    current = (
        session.query(TransactionCurrentVersion)
        .filter(
            TransactionCurrentVersion.o_id == org_id,
            TransactionCurrentVersion.transaction_id == "journey-corrected-transaction",
        )
        .one()
    )
    assert int(current.current_ed_id) == int(decisions[1].ed_id)
    assert int(current.current_ev_id) == int(decisions[1].ev_id)

    backtest = execute_backtest_rule_change(
        rule_id,
        "if $amount >= 125:\n\treturn !HOLD",
        org_id,
    )
    assert backtest["total_records"] == 2
    assert backtest["eligible_records"] == 2
    assert backtest["skipped_records"] == 0
    assert backtest["stored_result"] == {"HOLD": 1}
    assert backtest["proposed_result"] == {"HOLD": 1}

    original_result = (
        session.query(EvaluationRuleResult).filter(EvaluationRuleResult.ed_id == int(decisions[0].ed_id)).one()
    )
    assert original_result.rule_rid == "JOURNEY_CORRECTION_HOLD"
    assert original_result.rule_description == "Hold the original high amount"
    assert original_result.referenced_fields == ["amount"]


def test_agent_tool_replay_product_journey(session, live_api_key):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _seed_business_outcomes(session, org_id=org_id)
    token = _manager_token(session, email="journey-agent-tools@example.com")
    viewer_token = _token_with_permissions(
        session,
        email="journey-agent-viewer@example.com",
        permissions=[PermissionAction.VIEW_RULES],
    )

    with TestClient(app) as client:
        rule_id = _create_rule(
            client,
            token,
            rid="JOURNEY_AGENT_THRESHOLD",
            description="Hold high amount agent replay events",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        _promote_rule(client, token, rule_id)
        fraud_label = _create_label(client, token, label_name="journey_agent_fraud")
        normal_label = _create_label(client, token, label_name="journey_agent_normal")

        records = [
            ("journey-agent-fraud-high-us", 200, "US", fraud_label),
            ("journey-agent-normal-borderline-us", 130, "US", normal_label),
            ("journey-agent-normal-low-gb", 80, "GB", normal_label),
            ("journey-agent-fraud-high-gb", 170, "GB", fraud_label),
            ("journey-agent-fraud-borderline-gb", 120, "GB", fraud_label),
            ("journey-agent-fraud-missed-us", 60, "US", fraud_label),
        ]
        for transaction_id, amount, country, label_name in records:
            _evaluate(
                client,
                live_api_key,
                transaction_id=transaction_id,
                event_data={"amount": amount, "country": country},
            )
            _mark_event_label(client, token, transaction_id=transaction_id, label_name=label_name)

        _evaluate(
            client,
            live_api_key,
            transaction_id="journey-agent-rescored",
            observed_at="2026-05-05T12:01:00Z",
            event_data={"amount": 130, "country": "US"},
        )
        _mark_event_label(client, token, transaction_id="journey-agent-rescored", label_name=normal_label)
        _evaluate(
            client,
            live_api_key,
            transaction_id="journey-agent-rescored",
            observed_at="2026-05-05T12:30:00Z",
            event_data={"amount": 80, "country": "US"},
        )
        _mark_event_label(client, token, transaction_id="journey-agent-rescored", label_name=normal_label)

        other_org = Organisation(name="journey_agent_other_org")
        session.add(other_org)
        session.flush()
        add_served_decision(
            session,
            org_id=int(other_org.o_id),
            transaction_id="journey-agent-other-org",
            event_data={"amount": 130, "country": "LEAK"},
            resolved_outcome="HOLD",
            rule_results={rule_id: "HOLD"},
        )
        session.commit()

        before_invalid_counts = (
            session.query(EventVersion).count(),
            session.query(EvaluationDecision).count(),
            session.query(RuleBackTestingResult).count(),
        )
        invalid = client.post(
            "/api/v2/agent-tools/rule-blast-radius",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_id": rule_id, "proposed_logic": "if $amount >"},
        )
        assert invalid.status_code == 400
        assert (
            session.query(EventVersion).count(),
            session.query(EvaluationDecision).count(),
            session.query(RuleBackTestingResult).count(),
        ) == before_invalid_counts

        blast = client.post(
            "/api/v2/agent-tools/rule-blast-radius",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_id": rule_id,
                "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
                "group_by": ["country"],
                "sample_limit": 1,
                "max_records": 20,
            },
        )
        assert blast.status_code == 200
        blast_payload = blast.json()
        assert blast_payload["total_records"] == 7
        assert blast_payload["eligible_records"] == 7
        assert blast_payload["stored_result"] == {"HOLD": 4, "NO_OUTCOME": 3}
        assert blast_payload["proposed_result"] == {"HOLD": 2, "NO_OUTCOME": 5}
        assert blast_payload["changed_rule_outcome_count"] == 2
        assert len(blast_payload["flipped_events"]) == 1
        assert blast_payload["flipped_events"][0]["transaction_id"] in {
            "journey-agent-normal-borderline-us",
            "journey-agent-fraud-borderline-gb",
        }
        assert "journey-agent-rescored" not in {event["transaction_id"] for event in blast_payload["flipped_events"]}
        assert "journey-agent-other-org" not in {event["transaction_id"] for event in blast_payload["flipped_events"]}

        groups = {row["group"]["country"]: row for row in blast_payload["group_deltas"]}
        assert groups["US"]["changed_rule_outcome_count"] == 1
        assert groups["GB"]["changed_rule_outcome_count"] == 1

        counterexamples = client.post(
            "/api/v2/agent-tools/rule-counterexamples",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_id": rule_id,
                "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
                "positive_labels": [fraud_label],
                "negative_labels": [normal_label],
                "target_outcomes": ["HOLD"],
                "sample_limit": 10,
                "max_records": 20,
            },
        )
        assert counterexamples.status_code == 200
        buckets = counterexamples.json()["buckets"]
        assert {event["transaction_id"] for event in buckets["fired_but_negative"]} == {
            "journey-agent-normal-borderline-us"
        }
        assert {event["transaction_id"] for event in buckets["missed_positive"]} == {"journey-agent-fraud-missed-us"}
        assert {event["transaction_id"] for event in buckets["candidate_fixes_existing"]} == {
            "journey-agent-normal-borderline-us"
        }
        assert {event["transaction_id"] for event in buckets["candidate_introduces_new_errors"]} == {
            "journey-agent-fraud-borderline-gb"
        }

        viewer_blast = client.post(
            "/api/v2/agent-tools/rule-blast-radius",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "rule_id": rule_id,
                "proposed_logic": "if $amount > 150:\n\treturn !HOLD",
                "sample_limit": 10,
                "max_records": 20,
            },
        )
        assert viewer_blast.status_code == 200
        assert all(event["label_name"] is None for event in viewer_blast.json()["flipped_events"])

        viewer_counterexamples = client.post(
            "/api/v2/agent-tools/rule-counterexamples",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"rule_id": rule_id},
        )
        assert viewer_counterexamples.status_code == 403


def test_backtesting_with_computed_features_product_journey(session, live_api_key):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _seed_business_outcomes(session, org_id=org_id)
    token = _manager_token(session, email="journey-backtesting-feature@example.com")
    previous_always_eager = celery_app.conf.task_always_eager
    previous_eager_propagates = celery_app.conf.task_eager_propagates

    try:
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

        with TestClient(app) as client:
            _create_active_sum_feature(client, token)
            _add_feature_source_event(
                session,
                org_id=org_id,
                transaction_id="journey-backtest-feature-prior",
                effective_at=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
                event_data={"sender_id": "S1", "amount": 60},
            )
            session.commit()

            rule_id = _create_rule(
                client,
                token,
                rid="JOURNEY_BACKTEST_FEATURE_BASELINE",
                description="Baseline release rule for feature backtesting",
                logic="if $amount >= 0:\n\treturn !RELEASE",
            )
            _promote_rule(client, token, rule_id)
            fraud_label = _create_label(client, token, label_name="journey_backtest_fraud")

            _evaluate(
                client,
                live_api_key,
                transaction_id="journey-backtest-feature-hit",
                effective_at="2026-05-05T13:00:00Z",
                event_data={"sender_id": "S1", "amount": 5},
            )
            _mark_event_label(
                client,
                token,
                transaction_id="journey-backtest-feature-hit",
                label_name=fraud_label,
            )
            _evaluate(
                client,
                live_api_key,
                transaction_id="journey-backtest-missing-sender",
                effective_at="2026-05-05T14:00:00Z",
                event_data={"amount": 8},
            )

            trigger = client.post(
                "/api/v2/backtesting",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "r_id": rule_id,
                    "new_rule_logic": (
                        "if stat[sender.sent_amount_sum_24h] and stat[sender.sent_amount_sum_24h] > 50:\n\treturn !HOLD"
                    ),
                },
            )
            assert trigger.status_code == 200
            task_id = trigger.json()["task_id"]
            task_response = client.get(
                f"/api/v2/backtesting/task/{task_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert task_response.status_code == 200
            payload = task_response.json()
    finally:
        celery_app.conf.task_always_eager = previous_always_eager
        celery_app.conf.task_eager_propagates = previous_eager_propagates

    assert payload["queue_status"] == "done"
    assert payload["total_records"] == 1
    assert payload["eligible_records"] == 1
    assert payload["skipped_records"] == 1
    assert payload["stored_result"] == {"RELEASE": 1}
    assert payload["proposed_result"] == {"HOLD": 1}
    assert payload["label_counts"] == {fraud_label: 1}
    proposed_metric = next(
        metric
        for metric in payload["proposed_quality_metrics"]
        if metric["outcome"] == "HOLD" and metric["label"] == fraud_label
    )
    assert proposed_metric["true_positive"] == 1
    assert proposed_metric["precision"] == pytest.approx(1.0)
    assert proposed_metric["recall"] == pytest.approx(1.0)
    assert any("computed stats could not be resolved" in warning for warning in payload["warnings"])

    snapshot = payload["feature_snapshots"][0]
    assert snapshot["stat_path"] == "sender.sent_amount_sum_24h"
    assert snapshot["matched_event_count_min"] == 0
    assert snapshot["matched_event_count_max"] == 1
    assert snapshot["resolution_status_counts"] == {"failed": 1, "resolved": 1}
    assert payload["feature_snapshot_warnings"] == [
        "Event is missing entity key 'sender_id' required for stat[sender.sent_amount_sum_24h]"
    ]

    traces = (
        session.query(FeatureSnapshotResolution)
        .filter(FeatureSnapshotResolution.backtest_task_id == task_id)
        .order_by(FeatureSnapshotResolution.backtest_record_index.asc())
        .all()
    )
    assert [trace.resolution_status for trace in traces] == ["resolved", "failed"]


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
                "metadata_source": "evaluation_snapshot",
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
        feature_count = session.query(FeatureDefinition).filter(FeatureDefinition.o_id == int(org.o_id)).count()
        invalid_feature = client.post(
            "/api/v2/features",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={
                "name": "Invalid journey feature",
                "entity": "sender",
                "feature_name": "invalid_sent_amount_sum",
                "entity_key": "sender_id",
                "aggregation_type": "sum",
                "source_field": "amount",
                "window_seconds": 123,
            },
        )
        assert invalid_feature.status_code == 422
        assert session.query(FeatureDefinition).filter(FeatureDefinition.o_id == int(org.o_id)).count() == feature_count

        inactive_feature = client.post(
            "/api/v2/features",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={
                "name": "Inactive journey feature",
                "entity": "sender",
                "feature_name": "inactive_sent_amount_sum_24h",
                "entity_key": "sender_id",
                "aggregation_type": "sum",
                "source_field": "amount",
                "window_seconds": 86400,
            },
        )
        assert inactive_feature.status_code == 201
        assert inactive_feature.json()["feature"]["status"] == "draft"

        inactive_feature_rule = client.post(
            "/api/v2/rules",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={
                "rid": "JOURNEY_INACTIVE_FEATURE_RULE",
                "description": "Inactive feature rules should not persist",
                "logic": "if stat[sender.inactive_sent_amount_sum_24h] > 0:\n\treturn !HOLD",
                "evaluation_lane": "main",
            },
        )
        assert inactive_feature_rule.status_code == 201
        assert inactive_feature_rule.json()["success"] is False
        assert (
            session.query(RuleModel)
            .filter(RuleModel.o_id == int(org.o_id), RuleModel.rid == "JOURNEY_INACTIVE_FEATURE_RULE")
            .count()
            == 0
        )

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

        agent_rule_id = _create_rule(
            client,
            manager_token,
            rid="JOURNEY_AGENT_TOOL_SIDE_EFFECT_BASELINE",
            description="Baseline for invalid agent tool logic",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        before_agent_tool_failure = (
            session.query(EventVersion).count(),
            session.query(EvaluationDecision).count(),
            session.query(RuleBackTestingResult).count(),
        )
        invalid_agent_tool_logic = client.post(
            "/api/v2/agent-tools/rule-blast-radius",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={"rule_id": agent_rule_id, "proposed_logic": "if $amount >"},
        )
        assert invalid_agent_tool_logic.status_code == 400
        assert (
            session.query(EventVersion).count(),
            session.query(EvaluationDecision).count(),
            session.query(RuleBackTestingResult).count(),
        ) == before_agent_tool_failure

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

        label_count = session.query(Label).filter(Label.o_id == int(org.o_id)).count()
        forbidden_label = client.post(
            "/api/v2/labels",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"label_name": "journey_forbidden_label"},
        )
        assert forbidden_label.status_code == 403
        assert session.query(Label).filter(Label.o_id == int(org.o_id)).count() == label_count

        list_count = session.query(UserList).filter(UserList.o_id == int(org.o_id)).count()
        forbidden_list = client.post(
            "/api/v2/user-lists",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"name": "JourneyForbiddenList"},
        )
        assert forbidden_list.status_code == 403
        assert session.query(UserList).filter(UserList.o_id == int(org.o_id)).count() == list_count

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

        tested_events = client.get(
            "/api/v2/tested-events?limit=200&include_referenced_fields=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert tested_events.status_code == 200
        by_transaction = {event["transaction_id"]: event for event in tested_events.json()["events"]}
        assert by_transaction["journey-edit-before"]["triggered_rules"] == [
            {
                "r_id": rule_id,
                "rid": "JOURNEY_EDIT_RULE",
                "description": "Review high amount before edit",
                "outcome": "REVIEW",
                "metadata_source": "evaluation_snapshot",
                "referenced_fields": ["amount"],
            }
        ]
        assert by_transaction["journey-edit-after"]["triggered_rules"] == [
            {
                "r_id": rule_id,
                "rid": "JOURNEY_EDIT_RULE",
                "description": "Hold high amount after edit",
                "outcome": "HOLD",
                "metadata_source": "evaluation_snapshot",
                "referenced_fields": ["amount"],
            }
        ]

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
