import datetime
import hashlib
import uuid

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import analytics as analytics_routes
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    AllowedOutcome,
    ApiKey,
    ApiKeyHistory,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    EventVersionLabel,
    FieldObservation,
    FieldTypeHistory,
    Label,
    Organisation,
    OutcomeHistory,
    Role,
    Rule,
    RuleEngineConfig,
    RuleEngineConfigHistory,
    RuleHistory,
    RuleQualityPair,
    RuleQualityReport,
    RuntimeSetting,
    ShadowResultsLog,
    TestingRecordLog,
    TestingResultsLog,
    User,
    UserList,
    UserListEntry,
    UserListHistory,
)


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _create_org(session, prefix: str) -> Organisation:
    org = Organisation(name=f"{prefix}-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _grant_permissions(session, role: Role, permissions: list[PermissionAction]) -> None:
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)


def _create_user(
    session,
    *,
    org_id: int,
    email: str,
    permissions: list[PermissionAction],
    password: str = "phase2pass",
) -> User:
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    role = Role(
        name=f"phase2-role-{uuid.uuid4().hex[:8]}",
        description="Phase 2 org-scope role",
        o_id=org_id,
    )
    session.add(role)
    session.commit()
    _grant_permissions(session, role, permissions)

    user = User(
        email=email,
        password=hashed_password,
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=org_id,
    )
    user.roles.append(role)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name) for role in user.roles],
        org_id=int(user.o_id),
    )
    return {"Authorization": f"Bearer {token}"}


def _create_user_list(session, *, org_id: int, list_name: str, entries: list[str]) -> UserList:
    user_list = UserList(list_name=list_name, o_id=org_id)
    session.add(user_list)
    session.flush()
    for entry in entries:
        session.add(UserListEntry(entry_value=entry, ul_id=int(user_list.ul_id)))
    session.commit()
    session.refresh(user_list)
    return user_list


def _create_rule(
    session,
    *,
    org_id: int,
    rid: str,
    logic: str,
    description: str,
) -> Rule:
    rule = Rule(
        rid=rid,
        logic=logic,
        description=description,
        o_id=org_id,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def _save_production_config(session, org_id: int) -> None:
    rule_manager = RDBRuleManager(db=session, o_id=org_id)
    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
    config_producer.save_config(rule_manager)


def _create_api_key(session, *, org_id: int, label: str) -> tuple[str, ApiKey]:
    raw_key = "ezrk_" + uuid.uuid4().hex + uuid.uuid4().hex
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label=label,
        o_id=org_id,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return raw_key, api_key


def test_rules_use_auth_org_context_for_lists_and_rule_queries(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-rules-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-rules-admin"),
        permissions=[PermissionAction.VIEW_RULES],
    )
    other_user = _create_user(
        session,
        org_id=int(other_org.o_id),
        email=_unique_email("phase2-rules-other"),
        permissions=[PermissionAction.VIEW_RULES],
    )

    _create_user_list(session, org_id=int(org.o_id), list_name="Phase2Countries", entries=["GB"])
    _create_user_list(session, org_id=int(other_org.o_id), list_name="Phase2Countries", entries=["US"])

    org_rule = _create_rule(
        session,
        org_id=int(org.o_id),
        rid="PHASE2:ORG1",
        logic="return $amount > 10",
        description="Org 1 rule",
    )
    other_rule = _create_rule(
        session,
        org_id=int(other_org.o_id),
        rid="PHASE2:ORG2",
        logic="return $amount > 10",
        description="Org 2 rule",
    )

    session.add_all(
        [
            RuleHistory(
                r_id=int(org_rule.r_id),
                version=1,
                rid=str(org_rule.rid),
                logic=str(org_rule.logic),
                description=str(org_rule.description),
                o_id=int(org.o_id),
            ),
            RuleHistory(
                r_id=int(other_rule.r_id),
                version=1,
                rid=str(other_rule.rid),
                logic=str(other_rule.logic),
                description=str(other_rule.description),
                o_id=int(other_org.o_id),
            ),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        org_test_response = client.post(
            "/api/v2/rules/test",
            headers=_auth_headers(user),
            json={
                "rule_source": "return $country in @Phase2Countries",
                "test_json": '{"country": "GB"}',
            },
        )
        other_test_response = client.post(
            "/api/v2/rules/test",
            headers=_auth_headers(other_user),
            json={
                "rule_source": "return $country in @Phase2Countries",
                "test_json": '{"country": "GB"}',
            },
        )
        list_response = client.get("/api/v2/rules", headers=_auth_headers(user))
        hidden_response = client.get(f"/api/v2/rules/{other_rule.r_id}", headers=_auth_headers(user))
        history_response = client.get(f"/api/v2/rules/{org_rule.r_id}/history", headers=_auth_headers(user))

    assert org_test_response.status_code == 200
    assert org_test_response.json()["rule_outcome"] == "True"
    assert other_test_response.status_code == 200
    assert other_test_response.json()["rule_outcome"] == "False"

    observations = (
        session.query(FieldObservation)
        .filter(FieldObservation.field_name == "country")
        .order_by(FieldObservation.o_id.asc())
        .all()
    )
    assert [int(item.o_id) for item in observations] == [int(org.o_id), int(other_org.o_id)]

    assert list_response.status_code == 200
    listed_rids = {item["rid"] for item in list_response.json()["rules"]}
    assert "PHASE2:ORG1" in listed_rids
    assert "PHASE2:ORG2" not in listed_rids

    assert hidden_response.status_code == 404

    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload["r_id"] == int(org_rule.r_id)
    assert len(history_payload["history"]) >= 1
    assert history_payload["history"][-1]["is_current"] is True


def test_shadow_routes_and_tested_events_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-shadow-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-shadow-admin"),
        permissions=[PermissionAction.VIEW_RULES, PermissionAction.MODIFY_RULE],
    )

    org_rule = _create_rule(
        session,
        org_id=int(org.o_id),
        rid="PHASE2:SHADOW:ORG1",
        logic="return !ORG1_HOLD",
        description="Org 1 shadow rule",
    )
    other_rule = _create_rule(
        session,
        org_id=int(other_org.o_id),
        rid="PHASE2:SHADOW:ORG2",
        logic="return !ORG2_REVIEW",
        description="Org 2 shadow rule",
    )

    with TestClient(app) as client:
        deploy_response = client.post(f"/api/v2/rules/{org_rule.r_id}/shadow", headers=_auth_headers(user))
        hidden_deploy_response = client.post(f"/api/v2/rules/{other_rule.r_id}/shadow", headers=_auth_headers(user))

    assert deploy_response.status_code == 200
    assert hidden_deploy_response.status_code == 404

    session.add(
        RuleEngineConfig(
            label="shadow",
            config=[
                {
                    "r_id": int(other_rule.r_id),
                    "rid": str(other_rule.rid),
                    "description": str(other_rule.description),
                    "logic": str(other_rule.logic),
                }
            ],
            version=1,
            o_id=int(other_org.o_id),
        )
    )
    session.commit()

    org_event = TestingRecordLog(
        event_id=f"phase2-shadow-org1-{uuid.uuid4().hex[:6]}",
        event={"amount": 10},
        event_timestamp=1700000100,
        outcome_counters={"ORG1_HOLD": 1},
        resolved_outcome="ORG1_HOLD",
        o_id=int(org.o_id),
    )
    other_event = TestingRecordLog(
        event_id=f"phase2-shadow-org2-{uuid.uuid4().hex[:6]}",
        event={"amount": 20},
        event_timestamp=1700000200,
        outcome_counters={"ORG2_REVIEW": 1},
        resolved_outcome="ORG2_REVIEW",
        o_id=int(other_org.o_id),
    )
    session.add_all([org_event, other_event])
    session.commit()

    org_event_version = EventVersion(
        o_id=int(org.o_id),
        event_id=str(org_event.event_id),
        event_version=1,
        event_timestamp=int(org_event.event_timestamp),
        event_data=dict(org_event.event),
        payload_hash="0" * 64,
        source="evaluate",
    )
    other_event_version = EventVersion(
        o_id=int(other_org.o_id),
        event_id=str(other_event.event_id),
        event_version=1,
        event_timestamp=int(other_event.event_timestamp),
        event_data=dict(other_event.event),
        payload_hash="0" * 64,
        source="evaluate",
    )
    session.add_all([org_event_version, other_event_version])
    session.flush()
    org_decision = EvaluationDecision(
        ev_id=int(org_event_version.ev_id),
        tl_id=int(org_event.tl_id),
        o_id=int(org.o_id),
        event_id=str(org_event.event_id),
        event_version=1,
        event_timestamp=int(org_event.event_timestamp),
        decision_type="served",
        served=True,
        rule_config_label="production",
        outcome_counters={"ORG1_HOLD": 1},
        resolved_outcome="ORG1_HOLD",
    )
    other_decision = EvaluationDecision(
        ev_id=int(other_event_version.ev_id),
        tl_id=int(other_event.tl_id),
        o_id=int(other_org.o_id),
        event_id=str(other_event.event_id),
        event_version=1,
        event_timestamp=int(other_event.event_timestamp),
        decision_type="served",
        served=True,
        rule_config_label="production",
        outcome_counters={"ORG2_REVIEW": 1},
        resolved_outcome="ORG2_REVIEW",
    )
    session.add_all([org_decision, other_decision])
    session.flush()

    session.add_all(
        [
            TestingResultsLog(tl_id=int(org_event.tl_id), r_id=int(org_rule.r_id), rule_result="ORG1_HOLD"),
            TestingResultsLog(tl_id=int(other_event.tl_id), r_id=int(other_rule.r_id), rule_result="ORG2_REVIEW"),
            EvaluationRuleResult(ed_id=int(org_decision.ed_id), r_id=int(org_rule.r_id), rule_result="ORG1_HOLD"),
            EvaluationRuleResult(ed_id=int(other_decision.ed_id), r_id=int(other_rule.r_id), rule_result="ORG2_REVIEW"),
            ShadowResultsLog(tl_id=int(org_event.tl_id), r_id=int(org_rule.r_id), rule_result="ORG1_HOLD"),
            ShadowResultsLog(tl_id=int(other_event.tl_id), r_id=int(other_rule.r_id), rule_result="ORG2_REVIEW"),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        tested_events_response = client.get("/api/v2/tested-events", headers=_auth_headers(user))
        shadow_config_response = client.get("/api/v2/shadow", headers=_auth_headers(user))
        shadow_results_response = client.get("/api/v2/shadow/results", headers=_auth_headers(user))
        shadow_stats_response = client.get("/api/v2/shadow/stats", headers=_auth_headers(user))

    assert tested_events_response.status_code == 200
    tested_events_payload = tested_events_response.json()
    assert tested_events_payload["total"] == 1
    assert [item["event_id"] for item in tested_events_payload["events"]] == [str(org_event.event_id)]

    assert shadow_config_response.status_code == 200
    shadow_rule_ids = {item["r_id"] for item in shadow_config_response.json()["rules"]}
    assert shadow_rule_ids == {int(org_rule.r_id)}

    assert shadow_results_response.status_code == 200
    shadow_results_payload = shadow_results_response.json()
    assert shadow_results_payload["total"] == 1
    assert [item["event_id"] for item in shadow_results_payload["results"]] == [str(org_event.event_id)]

    assert shadow_stats_response.status_code == 200
    assert {item["r_id"] for item in shadow_stats_response.json()["rules"]} == {int(org_rule.r_id)}


def test_api_keys_and_evaluate_use_auth_derived_org(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-eval-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-api-keys-admin"),
        permissions=[PermissionAction.MANAGE_API_KEYS],
    )

    _create_rule(
        session,
        org_id=int(org.o_id),
        rid="PHASE2:EVAL:ORG1",
        logic="return !ORG1_HOLD",
        description="Org 1 evaluate rule",
    )
    _create_rule(
        session,
        org_id=int(other_org.o_id),
        rid="PHASE2:EVAL:ORG2",
        logic="return !ORG2_REVIEW",
        description="Org 2 evaluate rule",
    )
    _save_production_config(session, int(org.o_id))
    _save_production_config(session, int(other_org.o_id))

    other_raw_key, other_api_key = _create_api_key(session, org_id=int(other_org.o_id), label="other-org-eval")

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v2/api-keys",
            headers=_auth_headers(user),
            json={"label": "org1-managed-key"},
        )
        list_response = client.get("/api/v2/api-keys", headers=_auth_headers(user))
        org_eval_response = client.post(
            "/api/v2/evaluate",
            headers=_auth_headers(user),
            json={
                "event_id": "phase2-eval-org1",
                "event_timestamp": 1700000300,
                "event_data": {},
            },
        )
        other_eval_response = client.post(
            "/api/v2/evaluate",
            headers={"X-API-Key": other_raw_key},
            json={
                "event_id": "phase2-eval-org2",
                "event_timestamp": 1700000400,
                "event_data": {},
            },
        )

    assert create_response.status_code == 201
    created_gid = create_response.json()["gid"]
    created_key = session.query(ApiKey).filter(ApiKey.gid == created_gid).one()
    assert int(created_key.o_id) == int(org.o_id)

    assert list_response.status_code == 200
    listed_labels = {item["label"] for item in list_response.json()}
    assert "org1-managed-key" in listed_labels
    assert str(other_api_key.label) not in listed_labels

    assert org_eval_response.status_code == 200
    assert org_eval_response.json()["resolved_outcome"] == "ORG1_HOLD"
    assert other_eval_response.status_code == 200
    assert other_eval_response.json()["resolved_outcome"] == "ORG2_REVIEW"

    stored_events = (
        session.query(TestingRecordLog)
        .filter(TestingRecordLog.event_id.in_(["phase2-eval-org1", "phase2-eval-org2"]))
        .all()
    )
    org_ids_by_event = {str(event.event_id): int(event.o_id) for event in stored_events}
    assert org_ids_by_event == {
        "phase2-eval-org1": int(org.o_id),
        "phase2-eval-org2": int(other_org.o_id),
    }


def test_settings_runtime_and_rule_quality_pairs_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-settings-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-settings-admin"),
        permissions=[PermissionAction.VIEW_ROLES, PermissionAction.MANAGE_PERMISSIONS],
    )

    label = Label(label=f"PHASE2_SETTINGS_LABEL_{uuid.uuid4().hex[:6].upper()}")
    session.add(label)
    session.add_all(
        [
            RuntimeSetting(
                key="rule_quality_lookback_days",
                o_id=int(other_org.o_id),
                value_type="int",
                value="777",
            ),
            AllowedOutcome(outcome_name="ORG1_HOLD", severity_rank=1, o_id=int(org.o_id)),
            AllowedOutcome(outcome_name="ORG2_REVIEW", severity_rank=1, o_id=int(other_org.o_id)),
            RuleQualityPair(
                outcome="ORG2_REVIEW",
                label=str(label.label),
                active=True,
                created_by="tests",
                o_id=int(other_org.o_id),
            ),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        runtime_response = client.get("/api/v2/settings/runtime", headers=_auth_headers(user))
        update_runtime_response = client.put(
            "/api/v2/settings/runtime",
            headers=_auth_headers(user),
            json={"rule_quality_lookback_days": 21},
        )
        outcome_hierarchy_response = client.get("/api/v2/settings/outcome-hierarchy", headers=_auth_headers(user))
        create_pair_response = client.post(
            "/api/v2/settings/rule-quality-pairs",
            headers=_auth_headers(user),
            json={"outcome": "ORG1_HOLD", "label": str(label.label)},
        )
        list_pairs_response = client.get("/api/v2/settings/rule-quality-pairs", headers=_auth_headers(user))
        options_response = client.get("/api/v2/settings/rule-quality-pairs/options", headers=_auth_headers(user))

    assert runtime_response.status_code == 200
    assert runtime_response.json()["rule_quality_lookback_days"] != 777

    assert update_runtime_response.status_code == 200
    assert update_runtime_response.json()["rule_quality_lookback_days"] == 21

    runtime_settings = (
        session.query(RuntimeSetting)
        .filter(RuntimeSetting.key == "rule_quality_lookback_days")
        .order_by(RuntimeSetting.o_id.asc())
        .all()
    )
    assert [(int(item.o_id), str(item.value)) for item in runtime_settings] == [
        (int(org.o_id), "21"),
        (int(other_org.o_id), "777"),
    ]

    assert outcome_hierarchy_response.status_code == 200
    assert [item["outcome_name"] for item in outcome_hierarchy_response.json()["outcomes"]] == ["ORG1_HOLD"]

    assert create_pair_response.status_code == 200
    assert list_pairs_response.status_code == 200
    pair_outcomes = {item["outcome"] for item in list_pairs_response.json()["pairs"]}
    assert pair_outcomes == {"ORG1_HOLD"}

    assert options_response.status_code == 200
    assert options_response.json()["outcomes"] == ["ORG1_HOLD"]


def test_analytics_rule_quality_and_reports_are_org_scoped(session, monkeypatch):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-analytics-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-analytics-user"),
        permissions=[PermissionAction.VIEW_RULES, PermissionAction.VIEW_LABELS],
    )
    other_user = _create_user(
        session,
        org_id=int(other_org.o_id),
        email=_unique_email("phase2-analytics-other"),
        permissions=[PermissionAction.VIEW_RULES, PermissionAction.VIEW_LABELS],
    )

    label_name = f"PHASE2_ANALYTICS_LABEL_{uuid.uuid4().hex[:6].upper()}"
    org_label = Label(label=label_name, o_id=int(org.o_id))
    other_org_label = Label(label=label_name, o_id=int(other_org.o_id))
    session.add_all([org_label, other_org_label])
    session.commit()

    org_rule = _create_rule(
        session,
        org_id=int(org.o_id),
        rid="PHASE2:ANALYTICS:ORG1",
        logic="return !HOLD",
        description="Org 1 analytics rule",
    )
    other_rule = _create_rule(
        session,
        org_id=int(other_org.o_id),
        rid="PHASE2:ANALYTICS:ORG2",
        logic="return !REVIEW",
        description="Org 2 analytics rule",
    )

    now = datetime.datetime.utcnow()
    org_event = TestingRecordLog(
        event_id=f"phase2-analytics-org1-{uuid.uuid4().hex[:6]}",
        event={"amount": 100},
        event_timestamp=int(now.timestamp()),
        o_id=int(org.o_id),
        el_id=int(org_label.el_id),
        created_at=now,
    )
    other_event = TestingRecordLog(
        event_id=f"phase2-analytics-org2-{uuid.uuid4().hex[:6]}",
        event={"amount": 200},
        event_timestamp=int(now.timestamp()),
        o_id=int(other_org.o_id),
        el_id=int(other_org_label.el_id),
        created_at=now,
    )
    session.add_all([org_event, other_event])
    session.commit()

    org_event_version = EventVersion(
        o_id=int(org.o_id),
        event_id=str(org_event.event_id),
        event_version=1,
        event_timestamp=int(org_event.event_timestamp),
        event_data=dict(org_event.event),
        payload_hash="0" * 64,
        source="evaluate",
        ingested_at=now,
    )
    other_event_version = EventVersion(
        o_id=int(other_org.o_id),
        event_id=str(other_event.event_id),
        event_version=1,
        event_timestamp=int(other_event.event_timestamp),
        event_data=dict(other_event.event),
        payload_hash="0" * 64,
        source="evaluate",
        ingested_at=now,
    )
    session.add_all([org_event_version, other_event_version])
    session.flush()

    org_decision = EvaluationDecision(
        ev_id=int(org_event_version.ev_id),
        tl_id=int(org_event.tl_id),
        o_id=int(org.o_id),
        event_id=str(org_event.event_id),
        event_version=1,
        event_timestamp=int(org_event.event_timestamp),
        decision_type="served",
        served=True,
        rule_config_label="production",
        outcome_counters={"HOLD": 1},
        resolved_outcome="HOLD",
        all_rule_results={str(org_rule.r_id): "HOLD"},
        evaluated_at=now,
    )
    other_decision = EvaluationDecision(
        ev_id=int(other_event_version.ev_id),
        tl_id=int(other_event.tl_id),
        o_id=int(other_org.o_id),
        event_id=str(other_event.event_id),
        event_version=1,
        event_timestamp=int(other_event.event_timestamp),
        decision_type="served",
        served=True,
        rule_config_label="production",
        outcome_counters={"REVIEW": 1},
        resolved_outcome="REVIEW",
        all_rule_results={str(other_rule.r_id): "REVIEW"},
        evaluated_at=now,
    )
    session.add_all([org_decision, other_decision])
    session.flush()

    session.add_all(
        [
            TestingResultsLog(tl_id=int(org_event.tl_id), r_id=int(org_rule.r_id), rule_result="HOLD"),
            TestingResultsLog(tl_id=int(other_event.tl_id), r_id=int(other_rule.r_id), rule_result="REVIEW"),
            EvaluationRuleResult(ed_id=int(org_decision.ed_id), r_id=int(org_rule.r_id), rule_result="HOLD"),
            EvaluationRuleResult(ed_id=int(other_decision.ed_id), r_id=int(other_rule.r_id), rule_result="REVIEW"),
            EventVersionLabel(o_id=int(org.o_id), ev_id=int(org_event_version.ev_id), el_id=int(org_label.el_id)),
            EventVersionLabel(
                o_id=int(other_org.o_id),
                ev_id=int(other_event_version.ev_id),
                el_id=int(other_org_label.el_id),
            ),
            RuleQualityPair(
                outcome="HOLD",
                label=label_name,
                active=True,
                created_by="tests",
                o_id=int(org.o_id),
            ),
            RuleQualityPair(
                outcome="REVIEW",
                label=label_name,
                active=True,
                created_by="tests",
                o_id=int(other_org.o_id),
            ),
        ]
    )
    session.commit()

    def fake_delay(_report_id: int):
        class FakeResult:
            id = "phase2-rule-quality-task"

        return FakeResult()

    monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

    with TestClient(app) as client:
        transaction_volume_response = client.get("/api/v2/analytics/transaction-volume", headers=_auth_headers(user))
        rule_quality_response = client.get("/api/v2/analytics/rule-quality", headers=_auth_headers(user))
        create_report_response = client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers=_auth_headers(user),
            json={"min_support": 1, "lookback_days": 30, "force_refresh": True},
        )

        report_id = create_report_response.json()["report_id"]
        hidden_report_response = client.get(
            f"/api/v2/analytics/rule-quality/reports/{report_id}",
            headers=_auth_headers(other_user),
        )

    assert transaction_volume_response.status_code == 200
    assert sum(transaction_volume_response.json()["data"]) == 1

    assert rule_quality_response.status_code == 200
    quality_payload = rule_quality_response.json()
    assert quality_payload["total_labeled_events"] == 1
    assert {item["r_id"] for item in quality_payload["pair_metrics"]} == {int(org_rule.r_id)}

    assert create_report_response.status_code == 200
    created_report = session.query(RuleQualityReport).filter(RuleQualityReport.rqr_id == report_id).one()
    assert int(created_report.o_id) == int(org.o_id)

    assert hidden_report_response.status_code == 404


def test_audit_endpoints_only_return_current_org_history(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase2-audit-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase2-audit-admin"),
        permissions=[PermissionAction.ACCESS_AUDIT_TRAIL],
    )

    org_rule = _create_rule(
        session,
        org_id=int(org.o_id),
        rid="PHASE2:AUDIT:ORG1",
        logic="return True",
        description="Org 1 audit rule",
    )
    other_rule = _create_rule(
        session,
        org_id=int(other_org.o_id),
        rid="PHASE2:AUDIT:ORG2",
        logic="return True",
        description="Org 2 audit rule",
    )

    session.add_all(
        [
            RuleHistory(
                r_id=int(org_rule.r_id),
                version=1,
                rid=str(org_rule.rid),
                logic=str(org_rule.logic),
                description=str(org_rule.description),
                o_id=int(org.o_id),
            ),
            RuleHistory(
                r_id=int(other_rule.r_id),
                version=1,
                rid=str(other_rule.rid),
                logic=str(other_rule.logic),
                description=str(other_rule.description),
                o_id=int(other_org.o_id),
            ),
            RuleEngineConfigHistory(re_id=101, version=1, label="prod", config=[], o_id=int(org.o_id)),
            RuleEngineConfigHistory(re_id=202, version=1, label="prod", config=[], o_id=int(other_org.o_id)),
            UserListHistory(ul_id=1, list_name="Phase2Org1List", action="created", o_id=int(org.o_id)),
            UserListHistory(ul_id=2, list_name="Phase2Org2List", action="created", o_id=int(other_org.o_id)),
            OutcomeHistory(ao_id=1, outcome_name="ORG1_HOLD", action="created", o_id=int(org.o_id)),
            OutcomeHistory(ao_id=2, outcome_name="ORG2_REVIEW", action="created", o_id=int(other_org.o_id)),
            FieldTypeHistory(
                field_name="amount",
                configured_type="float",
                datetime_format=None,
                action="created",
                o_id=int(org.o_id),
            ),
            FieldTypeHistory(
                field_name="amount",
                configured_type="float",
                datetime_format=None,
                action="created",
                o_id=int(other_org.o_id),
            ),
            ApiKeyHistory(api_key_gid=str(uuid.uuid4()), label="org1-key", action="created", o_id=int(org.o_id)),
            ApiKeyHistory(api_key_gid=str(uuid.uuid4()), label="org2-key", action="created", o_id=int(other_org.o_id)),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        summary_response = client.get("/api/v2/audit", headers=_auth_headers(user))
        rules_response = client.get("/api/v2/audit/rules", headers=_auth_headers(user))
        rule_detail_response = client.get(f"/api/v2/audit/rules/{org_rule.r_id}", headers=_auth_headers(user))
        hidden_rule_detail_response = client.get(f"/api/v2/audit/rules/{other_rule.r_id}", headers=_auth_headers(user))
        config_response = client.get("/api/v2/audit/config", headers=_auth_headers(user))
        lists_response = client.get("/api/v2/audit/user-lists", headers=_auth_headers(user))
        outcomes_response = client.get("/api/v2/audit/outcomes", headers=_auth_headers(user))
        field_types_response = client.get("/api/v2/audit/field-types", headers=_auth_headers(user))
        api_keys_response = client.get("/api/v2/audit/api-keys", headers=_auth_headers(user))

    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["total_rule_versions"] == 1
    assert summary_payload["total_config_versions"] == 1
    assert summary_payload["rules_with_changes"] == 1
    assert summary_payload["configs_with_changes"] == 1
    assert summary_payload["total_user_list_actions"] == 1
    assert summary_payload["total_outcome_actions"] == 1
    assert summary_payload["total_field_type_actions"] == 1
    assert summary_payload["total_api_key_actions"] == 1

    assert rules_response.status_code == 200
    assert rules_response.json()["total"] == 1
    assert {item["r_id"] for item in rules_response.json()["items"]} == {int(org_rule.r_id)}

    assert rule_detail_response.status_code == 200
    assert rule_detail_response.json()["r_id"] == int(org_rule.r_id)
    assert hidden_rule_detail_response.status_code == 404

    assert config_response.status_code == 200
    assert config_response.json()["total"] == 1

    assert lists_response.status_code == 200
    assert lists_response.json()["total"] == 1
    assert {item["list_name"] for item in lists_response.json()["items"]} == {"Phase2Org1List"}

    assert outcomes_response.status_code == 200
    assert outcomes_response.json()["total"] == 1
    assert {item["outcome_name"] for item in outcomes_response.json()["items"]} == {"ORG1_HOLD"}

    assert field_types_response.status_code == 200
    assert field_types_response.json()["total"] == 1
    assert {item["field_name"] for item in field_types_response.json()["items"]} == {"amount"}

    assert api_keys_response.status_code == 200
    assert api_keys_response.json()["total"] == 1
    assert {item["label"] for item in api_keys_response.json()["items"]} == {"org1-key"}
