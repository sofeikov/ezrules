# ruff: noqa: F811

from datetime import UTC, datetime

import pytest

from ezrules.core.rule import OutcomeReturnSyntaxError
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager, save_rule_history
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import RuleEngineConfig, RuleHistory, RuleStatus
from tests.test_api_v2_rules import rules_test_client  # noqa: F401


def _auth_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.test_data['token']}"}


def _create_rule(session, *, rid: str, logic: str, status: RuleStatus) -> RuleModel:
    rule = RuleModel(
        rid=rid,
        logic=logic,
        description=f"Lifecycle contract for {rid}",
        status=status,
        effective_from=datetime.now(UTC) if status == RuleStatus.ACTIVE else None,
        o_id=1,
    )
    session.add(rule)
    session.commit()
    return rule


def _production_rule_ids(session) -> list[int]:
    config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == "production", RuleEngineConfig.o_id == 1)
        .one_or_none()
    )
    return [] if config is None else [int(entry["r_id"]) for entry in config.config]


@pytest.mark.parametrize(
    ("logic", "error_fragment"),
    [
        ("return $amount > 100", "direct configured outcome"),
        ("return !LEGACY_UNKNOWN", "is not configured in Outcomes"),
    ],
)
def test_legacy_invalid_draft_cannot_be_promoted(
    rules_test_client,
    logic: str,
    error_fragment: str,
) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(session, rid="legacy_invalid_draft", logic=logic, status=RuleStatus.DRAFT)

    response = rules_test_client.post(
        f"/api/v2/rules/{rule.r_id}/promote",
        headers=_auth_headers(rules_test_client),
    )

    assert response.status_code == 400
    assert error_fragment in response.json()["detail"]
    session.expire_all()
    assert session.get(RuleModel, rule.r_id).status == RuleStatus.DRAFT
    assert rule.r_id not in _production_rule_ids(session)
    assert session.query(RuleHistory).filter(RuleHistory.r_id == rule.r_id).count() == 0


def test_legacy_invalid_paused_rule_cannot_be_resumed(rules_test_client) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(
        session,
        rid="legacy_invalid_paused",
        logic="return $amount > 100",
        status=RuleStatus.PAUSED,
    )

    response = rules_test_client.post(
        f"/api/v2/rules/{rule.r_id}/resume",
        headers=_auth_headers(rules_test_client),
    )

    assert response.status_code == 400
    assert "direct configured outcome" in response.json()["detail"]
    session.expire_all()
    assert session.get(RuleModel, rule.r_id).status == RuleStatus.PAUSED
    assert rule.r_id not in _production_rule_ids(session)
    assert session.query(RuleHistory).filter(RuleHistory.r_id == rule.r_id).count() == 0


def test_invalid_historical_revision_can_be_restored_as_draft_but_not_promoted(rules_test_client) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(
        session,
        rid="legacy_invalid_history",
        logic="return $amount > 100",
        status=RuleStatus.ACTIVE,
    )
    save_rule_history(session, rule, changed_by="legacy-seed", action="updated", to_status=RuleStatus.ACTIVE)
    rule.logic = "return !HOLD"
    rule.version = 2
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=1).save_config(RDBRuleManager(db=session, o_id=1))

    rollback_response = rules_test_client.post(
        f"/api/v2/rules/{rule.r_id}/rollback",
        json={"revision_number": 1},
        headers=_auth_headers(rules_test_client),
    )
    promote_response = rules_test_client.post(
        f"/api/v2/rules/{rule.r_id}/promote",
        headers=_auth_headers(rules_test_client),
    )

    assert rollback_response.status_code == 200
    assert promote_response.status_code == 400
    assert "direct configured outcome" in promote_response.json()["detail"]
    session.expire_all()
    restored_rule = session.get(RuleModel, rule.r_id)
    assert restored_rule.logic == "return $amount > 100"
    assert restored_rule.status == RuleStatus.DRAFT
    assert rule.r_id not in _production_rule_ids(session)


@pytest.mark.parametrize(
    ("initial_status", "endpoint"),
    [
        (RuleStatus.DRAFT, "promote"),
        (RuleStatus.PAUSED, "resume"),
    ],
)
def test_valid_lifecycle_activation_still_updates_production(
    rules_test_client,
    initial_status: RuleStatus,
    endpoint: str,
) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(
        session,
        rid=f"valid_{endpoint}_control",
        logic="return !HOLD",
        status=initial_status,
    )

    response = rules_test_client.post(
        f"/api/v2/rules/{rule.r_id}/{endpoint}",
        headers=_auth_headers(rules_test_client),
    )

    assert response.status_code == 200
    session.expire_all()
    assert session.get(RuleModel, rule.r_id).status == RuleStatus.ACTIVE
    assert rule.r_id in _production_rule_ids(session)


def test_core_rule_manager_rejects_invalid_active_rule_before_commit(rules_test_client) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(
        session,
        rid="core_activation_defense",
        logic="return !HOLD",
        status=RuleStatus.DRAFT,
    )
    rule.logic = "return $amount > 100"
    rule.status = RuleStatus.ACTIVE

    with pytest.raises(OutcomeReturnSyntaxError, match="direct configured outcome"):
        RDBRuleManager(db=session, o_id=1).save_rule(rule)

    session.rollback()
    session.refresh(rule)
    assert rule.logic == "return !HOLD"
    assert rule.status == RuleStatus.DRAFT


def test_core_config_producer_rejects_direct_legacy_active_rule(rules_test_client) -> None:
    session = rules_test_client.test_data["session"]
    rule = _create_rule(
        session,
        rid="direct_config_activation_defense",
        logic="return $amount > 100",
        status=RuleStatus.ACTIVE,
    )

    with pytest.raises(OutcomeReturnSyntaxError, match="direct configured outcome"):
        RDBRuleEngineConfigProducer(db=session, o_id=1).save_config(RDBRuleManager(db=session, o_id=1))

    assert rule.r_id not in _production_rule_ids(session)
