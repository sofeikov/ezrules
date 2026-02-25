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
                .with_for_update()
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


RULE_MANAGERS = {
    "RDBRuleManager": RDBRuleManager,
}


class RuleManagerFactory:
    @staticmethod
    def get_rule_manager(rule_manager_type: str, **kwargs):
        return RULE_MANAGERS[rule_manager_type](**kwargs)
