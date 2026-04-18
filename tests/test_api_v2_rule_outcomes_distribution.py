import datetime

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, TestingRecordLog, TestingResultsLog, User
from ezrules.models.backend_core import Rule as RuleModel


def _create_rule_analytics_user(session, *, email: str, grant_view_rules: bool) -> User:
    hashed_password = bcrypt.hashpw("ruleperformancepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role_name = f"rule_performance_{email}"

    role = session.query(Role).filter(Role.name == role_name).first()
    if role is None:
        role = Role(name=role_name, description="Rule performance test role", o_id=1)
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            password=hashed_password,
            active=True,
            fs_uniquifier=email,
            o_id=1,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    if grant_view_rules:
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    return user


def _make_token_for_user(user: User) -> str:
    roles = [role.name for role in user.roles]
    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=roles,
        org_id=int(user.o_id),
    )


def _store_rule_result(
    session,
    *,
    org_id: int,
    rule: RuleModel,
    event_id: str,
    created_at: datetime.datetime,
    outcome: str,
) -> None:
    event = TestingRecordLog(
        event_id=event_id,
        event={"event_id": event_id},
        event_timestamp=int(created_at.timestamp()),
        o_id=org_id,
        created_at=created_at,
    )
    session.add(event)
    session.commit()

    session.add(
        TestingResultsLog(
            tl_id=event.tl_id,
            r_id=rule.r_id,
            rule_result=outcome,
        )
    )
    session.commit()


def test_rule_outcomes_distribution_returns_only_selected_rule_series(session):
    user = _create_rule_analytics_user(
        session,
        email="rule-performance@example.com",
        grant_view_rules=True,
    )
    token = _make_token_for_user(user)

    other_org = Organisation(o_id=2, name="rule-performance-other-org")
    session.add(other_org)
    session.commit()

    target_rule = RuleModel(
        rid="rule_performance_target",
        logic="return !HOLD",
        description="Target rule",
        o_id=1,
    )
    other_rule = RuleModel(
        rid="rule_performance_other",
        logic="return !RELEASE",
        description="Other org-one rule",
        o_id=1,
    )
    other_org_rule = RuleModel(
        rid="rule_performance_other_org",
        logic="return !REVIEW",
        description="Other org rule",
        o_id=2,
    )
    session.add_all([target_rule, other_rule, other_org_rule])
    session.commit()

    now = datetime.datetime.now()
    _store_rule_result(
        session,
        org_id=1,
        rule=target_rule,
        event_id="target-hold",
        created_at=now - datetime.timedelta(minutes=5),
        outcome="HOLD",
    )
    _store_rule_result(
        session,
        org_id=1,
        rule=target_rule,
        event_id="target-release",
        created_at=now - datetime.timedelta(minutes=10),
        outcome="RELEASE",
    )
    _store_rule_result(
        session,
        org_id=1,
        rule=target_rule,
        event_id="target-hold-2",
        created_at=now - datetime.timedelta(minutes=15),
        outcome="HOLD",
    )
    _store_rule_result(
        session,
        org_id=1,
        rule=other_rule,
        event_id="other-rule-event",
        created_at=now - datetime.timedelta(minutes=3),
        outcome="REVIEW",
    )
    _store_rule_result(
        session,
        org_id=2,
        rule=other_org_rule,
        event_id="other-org-event",
        created_at=now - datetime.timedelta(minutes=2),
        outcome="DECLINE",
    )
    _store_rule_result(
        session,
        org_id=1,
        rule=target_rule,
        event_id="target-old",
        created_at=now - datetime.timedelta(days=2),
        outcome="ESCALATE",
    )

    with TestClient(app) as client:
        response = client.get(
            f"/api/v2/analytics/rules/{target_rule.r_id}/outcomes-distribution?aggregation=6h",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload["aggregation"] == "6h"
    assert payload["labels"]
    assert [dataset["label"] for dataset in payload["datasets"]] == ["HOLD", "RELEASE"]
    totals = {dataset["label"]: sum(dataset["data"]) for dataset in payload["datasets"]}
    assert totals == {"HOLD": 2, "RELEASE": 1}


def test_rule_outcomes_distribution_rejects_invalid_aggregation(session):
    user = _create_rule_analytics_user(
        session,
        email="rule-performance-invalid@example.com",
        grant_view_rules=True,
    )
    token = _make_token_for_user(user)

    rule = RuleModel(
        rid="rule_performance_invalid_aggregation",
        logic="return !HOLD",
        description="Rule for invalid aggregation test",
        o_id=1,
    )
    session.add(rule)
    session.commit()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v2/analytics/rules/{rule.r_id}/outcomes-distribution?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 400


def test_rule_outcomes_distribution_requires_view_rules_permission(session):
    user = _create_rule_analytics_user(
        session,
        email="rule-performance-forbidden@example.com",
        grant_view_rules=False,
    )
    token = _make_token_for_user(user)

    rule = RuleModel(
        rid="rule_performance_forbidden",
        logic="return !HOLD",
        description="Rule for forbidden test",
        o_id=1,
    )
    session.add(rule)
    session.commit()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v2/analytics/rules/{rule.r_id}/outcomes-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


def test_rule_outcomes_distribution_returns_404_for_other_org_rule(session):
    user = _create_rule_analytics_user(
        session,
        email="rule-performance-not-found@example.com",
        grant_view_rules=True,
    )
    token = _make_token_for_user(user)

    other_org = Organisation(o_id=2, name="rule-performance-hidden-org")
    hidden_rule = RuleModel(
        rid="rule_performance_hidden",
        logic="return !HOLD",
        description="Hidden rule",
        o_id=2,
    )
    session.add_all([other_org, hidden_rule])
    session.commit()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v2/analytics/rules/{hidden_rule.r_id}/outcomes-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
