import datetime
from abc import ABC, abstractmethod
from collections import namedtuple

from sqlalchemy.exc import NoResultFound

from ezrules.core.rule import Rule, RuleConverter, RuleFactory
from ezrules.models.backend_core import (
    Organisation,
    RuleEngineConfig,
    RuleEngineConfigHistory,
    RuleHistory,
    ShadowResultsLog,
)
from ezrules.models.backend_core import (
    Rule as RuleModel,
)

RuleRevision = namedtuple("RuleRevision", ["revision_number", "created"])


def save_rule_history(db, rule: "RuleModel", changed_by: str | None = None) -> None:
    """Snapshot the current state of a rule into the history table before mutation."""
    history = RuleHistory(
        r_id=rule.r_id,
        version=rule.version,
        rid=rule.rid,
        logic=rule.logic,
        description=rule.description,
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
            .filter(RuleHistory.r_id == rule.r_id)
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

    def load_rule(self, rule_id: str, revision_number: int | None = None) -> RuleModel:
        if revision_number is None:
            latest_records = self.db.get(RuleModel, rule_id)
        else:
            latest_records = (
                self.db.query(RuleHistory)
                .filter(RuleHistory.r_id == rule_id, RuleHistory.version == revision_number)
                .order_by(RuleHistory.version)
                .one()
            )
        return latest_records

    def load_all_rules(self) -> list[RuleModel]:
        org = self.db.get(Organisation, self.o_id)
        return org.rules


class AbstractRuleEngineConfigProducer(ABC):
    @abstractmethod
    def save_config(self, rule_manager: RuleManager, changed_by: str | None = None) -> None:
        """Save config to a target location(disk, db, etc)."""


class RDBRuleEngineConfigProducer(AbstractRuleEngineConfigProducer):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id

    def save_config(self, rule_manager: RuleManager, changed_by: str | None = None) -> None:
        all_rules = rule_manager.load_all_rules()
        all_rules = [RuleFactory.from_json(r.__dict__) for r in all_rules]
        rules_json = [RuleConverter.to_json(r) for r in all_rules]
        try:
            config_obj = (
                self.db.query(RuleEngineConfig)
                .where(
                    RuleEngineConfig.label == "production",
                    RuleEngineConfig.o_id == self.o_id,
                )
                .one()
            )
            # Snapshot before mutation
            save_config_history(self.db, config_obj, changed_by=changed_by)
            config_obj.config = rules_json
            config_obj.version += 1
        except NoResultFound:
            new_config = RuleEngineConfig(label="production", config=rules_json, o_id=self.o_id)
            self.db.add(new_config)
        self.db.commit()


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
    rule_entry = {
        "r_id": rule_model.r_id,
        "rid": rule_model.rid,
        "logic": logic_override if logic_override is not None else rule_model.logic,
        "description": description_override if description_override is not None else rule_model.description,
    }
    try:
        config_obj = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "shadow",
                RuleEngineConfig.o_id == o_id,
            )
            .one()
        )
        save_config_history(db, config_obj, changed_by=changed_by)
        # If this rule was already in shadow, clear its result history so stats
        # reflect only the new version, not the previous one.
        if any(r.get("r_id") == rule_model.r_id for r in config_obj.config):
            db.query(ShadowResultsLog).filter(ShadowResultsLog.r_id == rule_model.r_id).delete()
        existing = [r for r in config_obj.config if r.get("r_id") != rule_model.r_id]
        existing.append(rule_entry)
        config_obj.config = existing
        config_obj.version += 1
    except NoResultFound:
        new_config = RuleEngineConfig(label="shadow", config=[rule_entry], o_id=o_id)
        db.add(new_config)
    db.commit()


def remove_rule_from_shadow(db, o_id: int, r_id: int, changed_by: str | None = None) -> None:
    """Remove a rule entry from the shadow config. No-op if not found."""
    try:
        config_obj = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "shadow",
                RuleEngineConfig.o_id == o_id,
            )
            .one()
        )
    except NoResultFound:
        return
    save_config_history(db, config_obj, changed_by=changed_by)
    config_obj.config = [r for r in config_obj.config if r.get("r_id") != r_id]
    config_obj.version += 1
    db.commit()


def promote_shadow_rule_to_production(db, o_id: int, r_id: int, changed_by: str | None = None) -> None:
    """Promote a rule from the shadow config into the production config.

    Raises ValueError if the rule is not currently in shadow.
    """
    try:
        shadow_config = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "shadow",
                RuleEngineConfig.o_id == o_id,
            )
            .one()
        )
    except NoResultFound as exc:
        raise ValueError(f"Rule {r_id} is not in shadow config (no shadow config exists)") from exc

    shadow_entry = next((r for r in shadow_config.config if r.get("r_id") == r_id), None)
    if shadow_entry is None:
        raise ValueError(f"Rule {r_id} is not in shadow config")

    # Update the rules table so the rule detail page reflects the promoted logic
    rule = db.get(RuleModel, r_id)
    if rule is not None:
        save_rule_history(db, rule, changed_by=changed_by)
        rule.logic = shadow_entry["logic"]
        rule.description = shadow_entry["description"]
        rule.version += 1

    try:
        prod_config = (
            db.query(RuleEngineConfig)
            .where(
                RuleEngineConfig.label == "production",
                RuleEngineConfig.o_id == o_id,
            )
            .one()
        )
        save_config_history(db, prod_config, changed_by=changed_by)
        existing = [r for r in prod_config.config if r.get("r_id") != r_id]
        existing.append(shadow_entry)
        prod_config.config = existing
        prod_config.version += 1
    except NoResultFound:
        new_prod = RuleEngineConfig(label="production", config=[shadow_entry], o_id=o_id)
        db.add(new_prod)

    remove_rule_from_shadow(db, o_id, r_id, changed_by=changed_by)


RULE_MANAGERS = {
    "RDBRuleManager": RDBRuleManager,
}


class RuleManagerFactory:
    @staticmethod
    def get_rule_manager(rule_manager_type: str, **kwargs):
        return RULE_MANAGERS[rule_manager_type](**kwargs)
