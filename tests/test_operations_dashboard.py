import datetime

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.operations_analytics import build_operations_summary
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Case,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    Organisation,
    Role,
    Rule,
    User,
)


def _add_rule(session, *, org_id: int, rid: str) -> Rule:
    rule = Rule(rid=rid, logic="return !HOLD", description=f"{rid} description", o_id=org_id)
    session.add(rule)
    session.flush()
    return rule


def _add_case(
    session,
    *,
    org_id: int,
    transaction_id: str,
    created_at: datetime.datetime,
    rules: list[Rule],
    status: str = "open",
    priority: int = 0,
    assignee: User | None = None,
    resolved_at: datetime.datetime | None = None,
    disposition: str | None = None,
) -> Case:
    event = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1,
        effective_at=created_at,
        observed_at=created_at,
        event_data={"transaction_id": transaction_id},
        payload_hash=f"{transaction_id:0<64}"[:64],
        ingested_at=created_at,
    )
    session.add(event)
    session.flush()
    decision = EvaluationDecision(
        ev_id=int(event.ev_id),
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1,
        effective_at=created_at,
        observed_at=created_at,
        decision_type="served",
        served=True,
        is_current=True,
        outcome_counters={"HOLD": len(rules)},
        resolved_outcome="HOLD",
        all_rule_results={str(rule.r_id): "HOLD" for rule in rules},
        evaluated_at=created_at,
    )
    session.add(decision)
    session.flush()
    for rule in rules:
        session.add(
            EvaluationRuleResult(
                ed_id=int(decision.ed_id),
                r_id=int(rule.r_id),
                rule_result="HOLD",
                rule_rid=str(rule.rid),
                rule_description=str(rule.description),
            )
        )
    case = Case(
        o_id=org_id,
        transaction_id=transaction_id,
        current_ev_id=int(event.ev_id),
        current_ed_id=int(decision.ed_id),
        opened_by_ed_id=int(decision.ed_id),
        resolved_outcome="HOLD",
        status=status,
        priority=priority,
        assigned_to_user_id=int(assignee.id) if assignee else None,
        resolution_disposition=disposition,
        created_at=created_at,
        updated_at=resolved_at or created_at,
        resolved_at=resolved_at,
    )
    session.add(case)
    session.flush()
    return case


def _add_api_user(session, *, has_view_cases: bool) -> str:
    role = Role(
        name=f"operations-{'viewer' if has_view_cases else 'blocked'}",
        description="Operations test role",
        o_id=1,
    )
    user = User(
        email=f"operations-{'viewer' if has_view_cases else 'blocked'}@example.com",
        password="unused",
        active=True,
        fs_uniquifier=f"operations-{'viewer' if has_view_cases else 'blocked'}@example.com",
        o_id=1,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    if has_view_cases:
        PermissionManager.grant_permission(int(role.id), PermissionAction.VIEW_CASES)
    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=1,
    )


def test_operations_summary_is_org_scoped_and_uses_documented_periods(session):
    now = datetime.datetime(2026, 7, 21, 14, 30, tzinfo=datetime.UTC)
    org_one = session.query(Organisation).filter(Organisation.o_id == 1).one()
    org_two = Organisation(o_id=2, name="Other org")
    session.add(org_two)
    session.flush()
    rule_one = _add_rule(session, org_id=int(org_one.o_id), rid="beneficiary_velocity")
    rule_two = _add_rule(session, org_id=int(org_two.o_id), rid="other_org_rule")
    assignee = User(
        email="analyst@example.com",
        password="unused",
        active=True,
        fs_uniquifier="analyst@example.com",
        o_id=1,
    )
    session.add(assignee)
    session.flush()

    active_unassigned = _add_case(
        session,
        org_id=1,
        transaction_id="active-unassigned",
        created_at=now - datetime.timedelta(days=3),
        rules=[rule_one],
        status="open",
        priority=4,
    )
    active_assigned = _add_case(
        session,
        org_id=1,
        transaction_id="active-assigned",
        created_at=now - datetime.timedelta(days=2),
        rules=[rule_one],
        status="in_review",
        priority=2,
        assignee=assignee,
    )
    _add_case(
        session,
        org_id=1,
        transaction_id="resolved-false-positive",
        created_at=now - datetime.timedelta(days=2),
        rules=[rule_one],
        status="resolved",
        resolved_at=now - datetime.timedelta(days=1),
        disposition="false_positive",
    )
    _add_case(
        session,
        org_id=1,
        transaction_id="resolved-confirmed",
        created_at=now - datetime.timedelta(days=1),
        rules=[rule_one],
        status="resolved",
        resolved_at=now - datetime.timedelta(hours=2),
        disposition="confirmed_fraud",
    )
    _add_case(
        session,
        org_id=1,
        transaction_id="resolved-before-window",
        created_at=now - datetime.timedelta(days=10),
        rules=[rule_one],
        status="resolved",
        resolved_at=now - datetime.timedelta(days=8),
        disposition="false_positive",
    )
    _add_case(
        session,
        org_id=2,
        transaction_id="other-org-active",
        created_at=now - datetime.timedelta(days=1),
        rules=[rule_two],
        status="open",
        priority=99,
    )
    rule_one.rid = "renamed_current_rule"
    rule_one.description = "Current metadata must not replace the opening snapshot"
    session.commit()

    result = build_operations_summary(session, o_id=1, days=7, now=now)

    assert result["period_start"] == datetime.datetime(2026, 7, 15, tzinfo=datetime.UTC)
    assert result["period_end"] == now
    assert result["summary"] == {
        "active_cases": 2,
        "unassigned_cases": 1,
        "resolved_cases": 2,
        "dispositioned_cases": 2,
        "false_positive_cases": 1,
        "false_positive_rate": 0.5,
    }
    assert len(result["case_flow"]) == 7
    assert sum(point["opened"] for point in result["case_flow"]) == 4
    assert sum(point["resolved"] for point in result["case_flow"]) == 2
    assert {item["case_id"] for item in result["attention_cases"]} == {
        int(active_unassigned.case_id),
        int(active_assigned.case_id),
    }
    assert [item["rid"] for item in result["noisy_rules"]] == ["beneficiary_velocity"]
    assert result["noisy_rules"][0]["case_count"] == 4
    assert result["noisy_rules"][0]["false_positive_rate"] == 0.5


def test_operations_summary_bounds_attention_and_deduplicates_rules(session):
    now = datetime.datetime(2026, 7, 21, 14, 30, tzinfo=datetime.UTC)
    rule_one = _add_rule(session, org_id=1, rid="velocity_rule")
    rule_two = _add_rule(session, org_id=1, rid="amount_rule")
    for index in range(12):
        _add_case(
            session,
            org_id=1,
            transaction_id=f"attention-{index:02d}",
            created_at=now - datetime.timedelta(hours=12 - index),
            rules=[rule_one, rule_two] if index == 0 else [rule_one],
            status="reopened" if index == 0 else "open",
            priority=5 if index < 2 else 1,
        )
    session.commit()

    result = build_operations_summary(session, o_id=1, days=30, now=now)

    assert len(result["attention_cases"]) == 10
    assert [item["age_seconds"] for item in result["attention_cases"][:2]] == [43_200, 39_600]
    rules = {item["rid"]: item for item in result["noisy_rules"]}
    assert rules["velocity_rule"]["case_count"] == 12
    assert rules["amount_rule"]["case_count"] == 1


def test_operations_summary_returns_null_rate_without_dispositions(session):
    result = build_operations_summary(
        session,
        o_id=1,
        days=30,
        now=datetime.datetime(2026, 7, 21, 14, 30, tzinfo=datetime.UTC),
    )

    assert result["summary"]["false_positive_rate"] is None
    assert result["case_flow"] == [
        {
            "date": datetime.date(2026, 6, 22) + datetime.timedelta(days=offset),
            "opened": 0,
            "resolved": 0,
        }
        for offset in range(30)
    ]
    assert result["attention_cases"] == []
    assert result["noisy_rules"] == []


def test_operations_summary_keeps_deleted_rules_in_case_attribution(session):
    now = datetime.datetime(2026, 7, 21, 14, 30, tzinfo=datetime.UTC)
    deleted_rule = _add_rule(session, org_id=1, rid="deleted_velocity_rule")
    deleted_rule_id = int(deleted_rule.r_id)
    _add_case(
        session,
        org_id=1,
        transaction_id="opened-before-rule-deletion",
        created_at=now - datetime.timedelta(days=1),
        rules=[deleted_rule],
    )
    session.query(EvaluationRuleResult).filter(EvaluationRuleResult.r_id == deleted_rule_id).delete()
    session.delete(deleted_rule)
    session.commit()

    result = build_operations_summary(session, o_id=1, days=7, now=now)

    assert result["noisy_rules"] == [
        {
            "rid": f"rule_{deleted_rule_id}",
            "description": "Deleted rule",
            "case_count": 1,
            "resolved_count": 0,
            "false_positive_count": 0,
            "false_positive_rate": None,
        }
    ]


def test_operations_endpoint_validates_days_and_requires_view_cases(session):
    viewer_token = _add_api_user(session, has_view_cases=True)
    blocked_token = _add_api_user(session, has_view_cases=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/v2/operations/summary?days=30",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200
        assert response.json()["days"] == 30

        invalid = client.get(
            "/api/v2/operations/summary?days=14",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert invalid.status_code == 422

        forbidden = client.get(
            "/api/v2/operations/summary?days=30",
            headers={"Authorization": f"Bearer {blocked_token}"},
        )
        assert forbidden.status_code == 403
