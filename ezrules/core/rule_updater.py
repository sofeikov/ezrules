import datetime
from abc import ABC, abstractmethod
from collections import namedtuple
from typing import Any, cast

from sqlalchemy.exc import NoResultFound

from ezrules.core.rule import Rule, RuleConverter, RuleFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import (
    Rule as RuleModel,
)
from ezrules.models.backend_core import (
    RuleDeploymentResultsLog,
    RuleEngineConfig,
    RuleEngineConfigHistory,
    RuleHistory,
    RuleStatus,
    ShadowResultsLog,
)

RuleRevision = namedtuple("RuleRevision", ["revision_number", "created"])

SHADOW_CONFIG_LABEL = "shadow"
ROLLOUT_CONFIG_LABEL = "rollout"
ALLOWLIST_CONFIG_LABEL = "allowlist"
DEPLOYMENT_MODE_SHADOW = "shadow"
DEPLOYMENT_MODE_SPLIT = "split"
DEPLOYMENT_VARIANT_CONTROL = "control"
DEPLOYMENT_VARIANT_CANDIDATE = "candidate"
RULE_EVALUATION_LANE_MAIN = "main"
RULE_EVALUATION_LANE_ALLOWLIST = "allowlist"


def save_rule_history(
    db,
    rule: "RuleModel",
    changed_by: str | None = None,
    action: str = "updated",
    to_status: RuleStatus | None = None,
    effective_from_override: datetime.datetime | None = None,
    approved_by_override: int | None = None,
    approved_at_override: datetime.datetime | None = None,
) -> None:
    """Snapshot the current state of a rule into the history table before mutation."""
    history = RuleHistory(
        r_id=rule.r_id,
        version=rule.version,
        rid=rule.rid,
        logic=rule.logic,
        description=rule.description,
        evaluation_lane=str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN),
        action=action,
        status=rule.status,
        to_status=to_status,
        effective_from=effective_from_override if effective_from_override is not None else rule.effective_from,
        approved_by=approved_by_override if approved_by_override is not None else rule.approved_by,
        approved_at=approved_at_override if approved_at_override is not None else rule.approved_at,
        created_at=rule.created_at,
        o_id=rule.o_id,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


def save_config_history(db, config: RuleEngineConfig, changed_by: str | None = None) -> None:
    """Snapshot the current state of a config into the history table before mutation."""
    history = RuleEngineConfigHistory(
        re_id=config.re_id,
        version=config.version,
        label=config.label,
        config=config.config,
        o_id=config.o_id,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


class RuleManager(ABC):
    """Abstract class for managing rules' lifecycle."""

    def save_rule(self, rule: Rule) -> None:
        """
        A wrapper around an abstract method :meth:`_save_rule`. The general flow is to lock the storage, \
        save the changes, and unlock the storage. By default, locking storage does nothing. It may be useful for \
        implementing a local file system rule manager where it is desirable to prevent race conditions. It is less \
        important when using a database as a target storage, but still may be useful in certain conditions.

        :param rule: an instance of `core.rule.Rule`
        :return:
        """
        self._save_rule(rule)

    @abstractmethod
    def _save_rule(self, rule: Rule) -> None:
        """Storage specific saving mechanism."""

    @abstractmethod
    def get_rule_revision_list(self, rule: Rule, return_dates=False) -> list[RuleRevision]:
        """Storage specific way to get a list of rule revisions.
        :param rule:
        :param return_dates:
        """

    @abstractmethod
    def load_rule(self, rule_id: str, revision_number: int | None = None) -> Rule:
        """Storage specific way to load a specific rule, possibly specific revision."""

    @abstractmethod
    def load_all_rules(self) -> list[Rule]:
        """Storage specific mechanism to load all available rules."""


class RDBRuleManager(RuleManager):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id

    def _save_rule(self, rule: RuleModel) -> None:
        if rule.r_id is None:
            rule.o_id = self.o_id
            self.db.add(rule)
        else:
            rule.version += 1
        self.db.commit()

    def get_rule_revision_list(self, rule: Rule, return_dates=False) -> list[RuleRevision]:
        revisions = (
            self.db.query(RuleHistory.version, RuleHistory.changed, RuleHistory.created_at)
            .filter(RuleHistory.r_id == rule.r_id, RuleHistory.o_id == self.o_id)
            .order_by(RuleHistory.version)
            .all()
        )
        version_list = []
        for ind, r in enumerate(revisions):
            if ind == 0:
                created = r.created_at
            else:
                created = revisions[ind - 1].changed
            version_list.append(RuleRevision(r.version, created))
        return version_list

    def load_rule(self, rule_id: int, revision_number: int | None = None) -> RuleModel:
        if revision_number is None:
            latest_records = (
                self.db.query(RuleModel).filter(RuleModel.r_id == rule_id, RuleModel.o_id == self.o_id).first()
            )
        else:
            latest_records = (
                self.db.query(RuleHistory)
                .filter(
                    RuleHistory.r_id == rule_id,
                    RuleHistory.version == revision_number,
                    RuleHistory.o_id == self.o_id,
                )
                .order_by(RuleHistory.version)
                .one()
            )
        return latest_records

    def load_all_rules(self) -> list[RuleModel]:
        return self.db.query(RuleModel).filter(RuleModel.o_id == self.o_id).all()


class AbstractRuleEngineConfigProducer(ABC):
    @abstractmethod
    def save_config(self, rule_manager: RuleManager, changed_by: str | None = None) -> None:
        """Save config to a target location(disk, db, etc)."""


class RDBRuleEngineConfigProducer(AbstractRuleEngineConfigProducer):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id

    def _save_rules_for_label(
        self, label: str, rules_json: list[dict[str, Any]], changed_by: str | None = None
    ) -> None:
        try:
            config_obj = (
                self.db.query(RuleEngineConfig)
                .where(
                    RuleEngineConfig.label == label,
                    RuleEngineConfig.o_id == self.o_id,
                )
                .with_for_update()
                .one()
            )
            save_config_history(self.db, config_obj, changed_by=changed_by)
            config_obj.config = rules_json
            config_obj.version += 1
        except NoResultFound:
            self.db.add(RuleEngineConfig(label=label, config=rules_json, o_id=self.o_id))

    def save_config(self, rule_manager: RuleManager, changed_by: str | None = None) -> None:
        stored_rules = cast(list[RuleModel], rule_manager.load_all_rules())
        list_provider = PersistentUserListManager(self.db, self.o_id)

        def _rules_json_for_lane(lane: str) -> list[dict[str, Any]]:
            active_rules = [
                rule
                for rule in stored_rules
                if rule.status == RuleStatus.ACTIVE
                and str(getattr(rule, "evaluation_lane", RULE_EVALUATION_LANE_MAIN) or RULE_EVALUATION_LANE_MAIN)
                == lane
            ]
            compiled_rules = [
                RuleFactory.from_json(r.__dict__, list_values_provider=list_provider) for r in active_rules
            ]
            return [RuleConverter.to_json(r) for r in compiled_rules]

        self._save_rules_for_label("production", _rules_json_for_lane(RULE_EVALUATION_LANE_MAIN), changed_by=changed_by)
        self._save_rules_for_label(
            ALLOWLIST_CONFIG_LABEL, _rules_json_for_lane(RULE_EVALUATION_LANE_ALLOWLIST), changed_by=changed_by
        )
        self.db.commit()


def _deployment_mode_from_label(label: str) -> str:
    if label == SHADOW_CONFIG_LABEL:
        return DEPLOYMENT_MODE_SHADOW
    if label == ROLLOUT_CONFIG_LABEL:
        return DEPLOYMENT_MODE_SPLIT
    raise ValueError(f"Unsupported deployment label: {label}")


def get_deployment_config(db, o_id: int, label: str, for_update: bool = False) -> RuleEngineConfig | None:
    query = db.query(RuleEngineConfig).where(
        RuleEngineConfig.label == label,
        RuleEngineConfig.o_id == o_id,
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def list_candidate_deployments(db, o_id: int, label: str) -> list[dict[str, Any]]:
    config_obj = get_deployment_config(db, o_id=o_id, label=label)
    if config_obj is None:
        return []
    return cast(list[dict[str, Any]], config_obj.config or [])


def list_all_candidate_deployments(db, o_id: int) -> list[dict[str, Any]]:
    return list_candidate_deployments(db, o_id=o_id, label=SHADOW_CONFIG_LABEL) + list_candidate_deployments(
        db, o_id=o_id, label=ROLLOUT_CONFIG_LABEL
    )


def get_candidate_deployment(db, o_id: int, r_id: int, label: str | None = None) -> dict[str, Any] | None:
    labels = [label] if label is not None else [SHADOW_CONFIG_LABEL, ROLLOUT_CONFIG_LABEL]
    for candidate_label in labels:
        for entry in list_candidate_deployments(db, o_id=o_id, label=candidate_label):
            if int(entry.get("r_id", -1)) == r_id:
                return entry
    return None


def get_candidate_deployment_label(db, o_id: int, r_id: int) -> str | None:
    for label in (SHADOW_CONFIG_LABEL, ROLLOUT_CONFIG_LABEL):
        if get_candidate_deployment(db, o_id=o_id, r_id=r_id, label=label) is not None:
            return label
    return None


def rule_has_candidate_deployment(db, o_id: int, r_id: int) -> bool:
    return get_candidate_deployment_label(db, o_id=o_id, r_id=r_id) is not None


def clear_rule_deployment_results(db, o_id: int, r_id: int) -> None:
    db.query(RuleDeploymentResultsLog).filter(
        RuleDeploymentResultsLog.o_id == o_id,
        RuleDeploymentResultsLog.r_id == r_id,
    ).delete()
    db.query(ShadowResultsLog).filter(ShadowResultsLog.r_id == r_id).delete()


def _build_deployment_entry(
    rule_model: "RuleModel",
    label: str,
    traffic_percent: int | None = None,
    logic_override: str | None = None,
    description_override: str | None = None,
    existing_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_snapshot = dict(existing_entry.get("control", {})) if existing_entry is not None else {}
    if not control_snapshot:
        control_snapshot = {
            "version": int(rule_model.version),
            "logic": str(rule_model.logic),
            "description": str(rule_model.description),
        }

    candidate_logic = (
        logic_override
        if logic_override is not None
        else str(existing_entry["logic"])
        if existing_entry is not None and "logic" in existing_entry
        else str(rule_model.logic)
    )
    candidate_description = (
        description_override
        if description_override is not None
        else str(existing_entry["description"])
        if existing_entry is not None and "description" in existing_entry
        else str(rule_model.description)
    )
    stored_traffic_percent = (
        traffic_percent
        if traffic_percent is not None
        else int(existing_entry["traffic_percent"])
        if existing_entry is not None and existing_entry.get("traffic_percent") is not None
        else None
    )

    return {
        "mode": _deployment_mode_from_label(label),
        "r_id": int(rule_model.r_id),
        "rid": str(rule_model.rid),
        "logic": candidate_logic,
        "description": candidate_description,
        "base_version": int(control_snapshot["version"]),
        "traffic_percent": stored_traffic_percent,
        "control": control_snapshot,
        "candidate": {
            "logic": candidate_logic,
            "description": candidate_description,
            "base_version": int(control_snapshot["version"]),
        },
    }


def _other_deployment_label(label: str) -> str:
    return ROLLOUT_CONFIG_LABEL if label == SHADOW_CONFIG_LABEL else SHADOW_CONFIG_LABEL


def upsert_candidate_deployment(
    db,
    o_id: int,
    label: str,
    rule_model: "RuleModel",
    changed_by: str | None = None,
    logic_override: str | None = None,
    description_override: str | None = None,
    traffic_percent: int | None = None,
) -> None:
    other_label = _other_deployment_label(label)
    other_entry = get_candidate_deployment(db, o_id=o_id, r_id=int(rule_model.r_id), label=other_label)
    if other_entry is not None:
        raise ValueError(f"Rule {rule_model.r_id} already has an active {other_label} deployment")

    config_obj = get_deployment_config(db, o_id=o_id, label=label, for_update=True)
    existing_entry = None
    if config_obj is not None:
        existing_entry = next(
            (entry for entry in config_obj.config if int(entry.get("r_id", -1)) == int(rule_model.r_id)), None
        )

    deployment_entry = _build_deployment_entry(
        rule_model=rule_model,
        label=label,
        traffic_percent=traffic_percent,
        logic_override=logic_override,
        description_override=description_override,
        existing_entry=existing_entry,
    )

    if config_obj is None:
        db.add(RuleEngineConfig(label=label, config=[deployment_entry], o_id=o_id))
    else:
        save_config_history(db, config_obj, changed_by=changed_by)
        if existing_entry is not None:
            clear_rule_deployment_results(db, o_id=o_id, r_id=int(rule_model.r_id))
        updated_entries = [entry for entry in config_obj.config if int(entry.get("r_id", -1)) != int(rule_model.r_id)]
        updated_entries.append(deployment_entry)
        config_obj.config = updated_entries
        config_obj.version += 1
    db.commit()


def remove_candidate_deployment(
    db,
    o_id: int,
    r_id: int,
    label: str,
    changed_by: str | None = None,
) -> None:
    config_obj = get_deployment_config(db, o_id=o_id, label=label, for_update=True)
    if config_obj is None:
        return

    existing_entry = next((entry for entry in config_obj.config if int(entry.get("r_id", -1)) == r_id), None)
    if existing_entry is None:
        return

    save_config_history(db, config_obj, changed_by=changed_by)
    config_obj.config = [entry for entry in config_obj.config if int(entry.get("r_id", -1)) != r_id]
    config_obj.version += 1
    clear_rule_deployment_results(db, o_id=o_id, r_id=r_id)
    db.commit()


def promote_candidate_deployment_to_production(
    db,
    o_id: int,
    r_id: int,
    label: str,
    changed_by: str | None = None,
    approved_by: int | None = None,
) -> None:
    config_obj = get_deployment_config(db, o_id=o_id, label=label, for_update=True)
    if config_obj is None:
        raise ValueError(f"Rule {r_id} is not in {label} config (no {label} config exists)")

    deployment_entry = next((entry for entry in config_obj.config if int(entry.get("r_id", -1)) == r_id), None)
    if deployment_entry is None:
        raise ValueError(f"Rule {r_id} is not in {label} config")

    rule = db.query(RuleModel).filter(RuleModel.r_id == r_id, RuleModel.o_id == o_id).first()
    if rule is None:
        raise ValueError(f"Rule {r_id} does not exist")

    promoted_at = datetime.datetime.now(datetime.UTC)
    save_rule_history(
        db,
        rule,
        changed_by=changed_by,
        action="promoted",
        to_status=RuleStatus.ACTIVE,
        effective_from_override=promoted_at,
        approved_by_override=approved_by,
        approved_at_override=promoted_at,
    )
    rule.logic = str(deployment_entry["logic"])
    rule.description = str(deployment_entry["description"])
    rule.status = RuleStatus.ACTIVE
    rule.effective_from = promoted_at
    rule.approved_by = approved_by
    rule.approved_at = promoted_at
    rule.version += 1

    prod_entry = {
        "r_id": int(rule.r_id),
        "rid": str(rule.rid),
        "logic": str(rule.logic),
        "description": str(rule.description),
    }
    prod_config = get_deployment_config(db, o_id=o_id, label="production", for_update=True)
    if prod_config is None:
        db.add(RuleEngineConfig(label="production", config=[prod_entry], o_id=o_id))
    else:
        save_config_history(db, prod_config, changed_by=changed_by)
        updated_prod_entries = [entry for entry in prod_config.config if int(entry.get("r_id", -1)) != r_id]
        updated_prod_entries.append(prod_entry)
        prod_config.config = updated_prod_entries
        prod_config.version += 1

    save_config_history(db, config_obj, changed_by=changed_by)
    config_obj.config = [entry for entry in config_obj.config if int(entry.get("r_id", -1)) != r_id]
    config_obj.version += 1
    clear_rule_deployment_results(db, o_id=o_id, r_id=r_id)
    db.commit()


def deploy_rule_to_shadow(
    db,
    o_id: int,
    rule_model: "RuleModel",
    changed_by: str | None = None,
    logic_override: str | None = None,
    description_override: str | None = None,
) -> None:
    """Deploy a rule version to the shadow config for the given organisation.

    Creates the shadow RuleEngineConfig if it does not yet exist.
    Replaces any existing entry for the rule's r_id.
    If logic_override or description_override are provided they are stored in
    shadow instead of the values from rule_model (allowing draft logic to be
    deployed without touching the rules table or production config).
    """
    upsert_candidate_deployment(
        db=db,
        o_id=o_id,
        label=SHADOW_CONFIG_LABEL,
        rule_model=rule_model,
        changed_by=changed_by,
        logic_override=logic_override,
        description_override=description_override,
    )


def remove_rule_from_shadow(db, o_id: int, r_id: int, changed_by: str | None = None) -> None:
    """Remove a rule entry from the shadow config. No-op if not found."""
    remove_candidate_deployment(db=db, o_id=o_id, r_id=r_id, label=SHADOW_CONFIG_LABEL, changed_by=changed_by)


def promote_shadow_rule_to_production(
    db,
    o_id: int,
    r_id: int,
    changed_by: str | None = None,
    approved_by: int | None = None,
) -> None:
    """Promote a rule from the shadow config into the production config.

    Raises ValueError if the rule is not currently in shadow.
    """
    promote_candidate_deployment_to_production(
        db=db,
        o_id=o_id,
        r_id=r_id,
        label=SHADOW_CONFIG_LABEL,
        changed_by=changed_by,
        approved_by=approved_by,
    )


def deploy_rule_to_rollout(
    db,
    o_id: int,
    rule_model: "RuleModel",
    traffic_percent: int,
    changed_by: str | None = None,
    logic_override: str | None = None,
    description_override: str | None = None,
) -> None:
    upsert_candidate_deployment(
        db=db,
        o_id=o_id,
        label=ROLLOUT_CONFIG_LABEL,
        rule_model=rule_model,
        changed_by=changed_by,
        logic_override=logic_override,
        description_override=description_override,
        traffic_percent=traffic_percent,
    )


def remove_rule_from_rollout(db, o_id: int, r_id: int, changed_by: str | None = None) -> None:
    remove_candidate_deployment(db=db, o_id=o_id, r_id=r_id, label=ROLLOUT_CONFIG_LABEL, changed_by=changed_by)


def promote_rollout_rule_to_production(
    db,
    o_id: int,
    r_id: int,
    changed_by: str | None = None,
    approved_by: int | None = None,
) -> None:
    promote_candidate_deployment_to_production(
        db=db,
        o_id=o_id,
        r_id=r_id,
        label=ROLLOUT_CONFIG_LABEL,
        changed_by=changed_by,
        approved_by=approved_by,
    )


RULE_MANAGERS = {
    "RDBRuleManager": RDBRuleManager,
}


class RuleManagerFactory:
    @staticmethod
    def get_rule_manager(rule_manager_type: str, **kwargs):
        return RULE_MANAGERS[rule_manager_type](**kwargs)
