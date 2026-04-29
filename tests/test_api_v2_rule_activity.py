import datetime

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Organisation,
    Role,
    RuleStatus,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


def _create_event(
    session,
    *,
    org_id: int,
    event_id: str,
    created_at: datetime.datetime,
    fired_rules: list[RuleModel],
) -> None:
    add_served_decision(
        session,
        org_id=org_id,
        event_id=event_id,
        event_data={"event_id": event_id},
        event_timestamp=int(created_at.timestamp()),
        evaluated_at=created_at,
        rule_results={int(rule.r_id): "HOLD" for rule in fired_rules},
    )
    session.commit()


def _make_token_for_user(user: User) -> str:
    roles = [role.name for role in user.roles]
    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=roles,
        org_id=int(user.o_id),
    )


def _create_rule_activity_user(session, *, email: str, grant_view_rules: bool) -> User:
    hashed_password = bcrypt.hashpw("ruleactivitypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role_name = f"rule_activity_{email}"

    role = session.query(Role).filter(Role.name == role_name).first()
    if role is None:
        role = Role(name=role_name, description="Rule activity test role", o_id=1)
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


def test_rule_activity_returns_ranked_active_rules_including_zero_hits(session):
    user = _create_rule_activity_user(
        session,
        email="ruleactivity@example.com",
        grant_view_rules=True,
    )
    token = _make_token_for_user(user)

    now = datetime.datetime.now()
    alpha_rule = RuleModel(
        rid="alpha_active",
        logic="return !HOLD",
        description="Alpha active rule",
        o_id=1,
        status=RuleStatus.ACTIVE,
    )
    beta_rule = RuleModel(
        rid="beta_active",
        logic="return !HOLD",
        description="Beta active rule",
        o_id=1,
        status=RuleStatus.ACTIVE,
    )
    gamma_rule = RuleModel(
        rid="gamma_active",
        logic="return !HOLD",
        description="Gamma active rule",
        o_id=1,
        status=RuleStatus.ACTIVE,
    )
    delta_rule = RuleModel(
        rid="delta_active",
        logic="return !HOLD",
        description="Delta active rule",
        o_id=1,
        status=RuleStatus.ACTIVE,
    )
    draft_rule = RuleModel(
        rid="draft_rule",
        logic="return !HOLD",
        description="Draft rule",
        o_id=1,
        status=RuleStatus.DRAFT,
    )
    archived_rule = RuleModel(
        rid="archived_rule",
        logic="return !HOLD",
        description="Archived rule",
        o_id=1,
        status=RuleStatus.ARCHIVED,
    )
    paused_rule = RuleModel(
        rid="paused_rule",
        logic="return !HOLD",
        description="Paused rule",
        o_id=1,
        status=RuleStatus.PAUSED,
    )
    other_org = Organisation(o_id=2, name="other_org")
    other_org_rule = RuleModel(
        rid="other_org_rule",
        logic="return !HOLD",
        description="Other org rule",
        o_id=2,
        status=RuleStatus.ACTIVE,
    )
    session.add_all(
        [
            alpha_rule,
            beta_rule,
            gamma_rule,
            delta_rule,
            draft_rule,
            archived_rule,
            paused_rule,
            other_org,
            other_org_rule,
        ]
    )
    session.commit()

    _create_event(
        session,
        org_id=1,
        event_id="rule-activity-1",
        created_at=now - datetime.timedelta(minutes=10),
        fired_rules=[alpha_rule, beta_rule, draft_rule],
    )
    _create_event(
        session,
        org_id=1,
        event_id="rule-activity-2",
        created_at=now - datetime.timedelta(minutes=20),
        fired_rules=[alpha_rule, beta_rule],
    )
    _create_event(
        session,
        org_id=1,
        event_id="rule-activity-3",
        created_at=now - datetime.timedelta(minutes=30),
        fired_rules=[delta_rule],
    )
    _create_event(
        session,
        org_id=1,
        event_id="rule-activity-old",
        created_at=now - datetime.timedelta(days=2),
        fired_rules=[alpha_rule, archived_rule],
    )
    for idx in range(4):
        _create_event(
            session,
            org_id=2,
            event_id=f"other-org-{idx}",
            created_at=now - datetime.timedelta(minutes=idx),
            fired_rules=[other_org_rule],
        )

    with TestClient(app) as client:
        response = client.get(
            "/api/v2/analytics/rule-activity?aggregation=6h&limit=3",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload["aggregation"] == "6h"
    assert payload["limit"] == 3
    assert [item["rid"] for item in payload["most_firing"]] == ["alpha_active", "beta_active", "delta_active"]
    assert [item["fire_count"] for item in payload["most_firing"]] == [2, 2, 1]
    assert [item["rid"] for item in payload["least_firing"]] == ["gamma_active", "delta_active", "alpha_active"]
    assert [item["fire_count"] for item in payload["least_firing"]] == [0, 1, 2]

    returned_rule_ids = {
        item["rid"] for ranking in (payload["most_firing"], payload["least_firing"]) for item in ranking
    }
    assert "draft_rule" not in returned_rule_ids
    assert "paused_rule" not in returned_rule_ids
    assert "archived_rule" not in returned_rule_ids
    assert "other_org_rule" not in returned_rule_ids


def test_rule_activity_rejects_invalid_aggregation(session):
    user = _create_rule_activity_user(
        session,
        email="ruleactivity-invalid@example.com",
        grant_view_rules=True,
    )
    token = _make_token_for_user(user)

    with TestClient(app) as client:
        response = client.get(
            "/api/v2/analytics/rule-activity?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 400


def test_rule_activity_requires_view_rules_permission(session):
    user = _create_rule_activity_user(
        session,
        email="ruleactivity-forbidden@example.com",
        grant_view_rules=False,
    )
    token = _make_token_for_user(user)

    with TestClient(app) as client:
        response = client.get(
            "/api/v2/analytics/rule-activity",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
