import bcrypt
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import deploy_rule_to_rollout
from ezrules.models.backend_core import (
    Organisation,
    Role,
    Rule as RuleModel,
    RuleDeploymentResultsLog,
    RuleStatus,
    User,
)
from ezrules.models.backend_core import EvaluationDecision
from tests.canonical_helpers import add_served_decision


def _view_headers(session) -> dict[str, str]:
    hashed_password = bcrypt.hashpw("reviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "review_viewer").first()
    if role is None:
        role = Role(name="review_viewer", description="Can view rollout and shadow stats")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "review-viewer@example.com").first()
    if user is None:
        user = User(
            email="review-viewer@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="review-viewer@example.com",
            o_id=1,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )
    return {"Authorization": f"Bearer {token}"}


def _create_rule(
    session,
    *,
    rid: str,
    logic: str,
    description: str,
    status: RuleStatus = RuleStatus.ACTIVE,
) -> RuleModel:
    rule = RuleModel(
        rid=rid,
        logic=logic,
        description=description,
        status=status,
        effective_from=datetime.now(UTC) if status == RuleStatus.ACTIVE else None,
        o_id=1,
    )
    session.add(rule)
    session.commit()
    return rule


def _create_decision(session, *, event_id: str, outcome: str | None = None) -> EvaluationDecision:
    decision = add_served_decision(
        session,
        org_id=1,
        event_id=event_id,
        event_data={"amount": 100},
        event_timestamp=1700000000,
        outcome_counters={outcome: 1} if outcome is not None else None,
        resolved_outcome=outcome,
    )
    session.commit()
    return decision


def test_shadow_results_and_stats_use_canonical_deployment_logs(session):
    headers = _view_headers(session)
    rule = _create_rule(
        session,
        rid="REVIEW:SHADOW:001",
        logic="return !CONTROL",
        description="Rule for shadow regression coverage",
    )

    decision = _create_decision(session, event_id="shadow-shared-event", outcome="CONTROL_A")

    session.add_all(
        [
            RuleDeploymentResultsLog(
                ed_id=int(decision.ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="shadow",
                selected_variant="control",
                control_result="CONTROL_A",
                candidate_result="SHARED_CANDIDATE",
                returned_result="CONTROL_A",
            ),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        results_response = client.get("/api/v2/shadow/results?limit=10", headers=headers)
        stats_response = client.get("/api/v2/shadow/stats", headers=headers)

    assert results_response.status_code == 200
    results_payload = results_response.json()
    assert results_payload["total"] == 1

    results_by_event = {item["event_id"]: item["rule_result"] for item in results_payload["results"]}
    assert results_by_event == {
        "shadow-shared-event": "SHARED_CANDIDATE",
    }

    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert len(stats_payload["rules"]) == 1
    rule_stats = stats_payload["rules"][0]
    assert rule_stats["r_id"] == int(rule.r_id)
    assert rule_stats["total"] == 1
    assert {item["outcome"]: item["count"] for item in rule_stats["shadow_outcomes"]} == {
        "SHARED_CANDIDATE": 1,
    }
    assert {item["outcome"]: item["count"] for item in rule_stats["prod_outcomes"]} == {
        "CONTROL_A": 1,
    }


def test_rollout_stats_aggregate_counts_in_sql(session):
    headers = _view_headers(session)
    rule = _create_rule(
        session,
        rid="REVIEW:ROLLOUT:001",
        logic="return !CONTROL",
        description="Rule for rollout aggregation coverage",
    )

    deploy_rule_to_rollout(
        db=session,
        o_id=1,
        rule_model=rule,
        traffic_percent=40,
        changed_by="test",
        logic_override="return !CANDIDATE",
        description_override="Candidate rollout",
    )

    events = [
        _create_decision(session, event_id="rollout-event-1", outcome="REVIEW"),
        _create_decision(session, event_id="rollout-event-2", outcome="REVIEW"),
        _create_decision(session, event_id="rollout-event-3", outcome="HOLD"),
        _create_decision(session, event_id="rollout-event-4", outcome="HOLD"),
    ]

    session.add_all(
        [
            RuleDeploymentResultsLog(
                ed_id=int(events[0].ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="split",
                selected_variant="candidate",
                traffic_percent=40,
                bucket=3,
                control_result="HOLD",
                candidate_result="REVIEW",
                returned_result="REVIEW",
            ),
            RuleDeploymentResultsLog(
                ed_id=int(events[1].ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="split",
                selected_variant="candidate",
                traffic_percent=40,
                bucket=17,
                control_result="HOLD",
                candidate_result="REVIEW",
                returned_result="REVIEW",
            ),
            RuleDeploymentResultsLog(
                ed_id=int(events[2].ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="split",
                selected_variant="control",
                traffic_percent=40,
                bucket=61,
                control_result="HOLD",
                candidate_result="REVIEW",
                returned_result="HOLD",
            ),
            RuleDeploymentResultsLog(
                ed_id=int(events[3].ed_id),
                r_id=int(rule.r_id),
                o_id=1,
                mode="split",
                selected_variant="control",
                traffic_percent=40,
                bucket=88,
                control_result="HOLD",
                candidate_result="BLOCK",
                returned_result="HOLD",
            ),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        stats_response = client.get("/api/v2/rollouts/stats", headers=headers)

    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert len(stats_payload["rules"]) == 1

    rule_stats = stats_payload["rules"][0]
    assert rule_stats["r_id"] == int(rule.r_id)
    assert rule_stats["traffic_percent"] == 40
    assert rule_stats["total"] == 4
    assert rule_stats["served_candidate"] == 2
    assert rule_stats["served_control"] == 2
    assert {item["outcome"]: item["count"] for item in rule_stats["candidate_outcomes"]} == {
        "REVIEW": 3,
        "BLOCK": 1,
    }
    assert {item["outcome"]: item["count"] for item in rule_stats["control_outcomes"]} == {
        "HOLD": 4,
    }
