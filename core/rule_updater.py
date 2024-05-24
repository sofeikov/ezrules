from abc import ABC, abstractmethod
from core.rule import Rule, RuleFactory, RuleConverter
from typing import Optional, List, Union
import hashlib
from ruamel.yaml import scalarstring
from datetime import datetime
import ruamel
import yaml
import operator
from collections import namedtuple
from sqlalchemy.exc import NoResultFound

from models.backend_core import (
    RuleEngineConfig,
    Rule as RuleModel,
    Organisation,
    RuleHistory,
)

RuleRevision = namedtuple("RuleRevision", ["revision_number", "created"])


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
        self.lock_storage()
        self._save_rule(rule)
        self.release_storage()

    def lock_storage(self):
        """Lock storage. Override in subclasses if lock is required."""
        pass

    def release_storage(self):
        """Unlock storage. Override in subclasses if lock is required."""
        pass

    @abstractmethod
    def _save_rule(self, rule: Rule) -> None:
        """Storage specific saving mechanism."""

    @abstractmethod
    def get_rule_revision_list(
        self, rule: Rule, return_dates=False
    ) -> List[RuleRevision]:
        """Storage specific way to get a list of rule revisions.
        :param rule:
        :param return_dates:
        """

    @abstractmethod
    def load_rule(self, rule_id: str, revision_number: Optional[str] = None) -> Rule:
        """Storage specific way to load a specific rule, possibly specific revision."""

    @abstractmethod
    def load_all_rules(self) -> List[Rule]:
        """Storage specific mechanism to load all available rules."""


class AbstractRuleEngineConfigProducer(ABC):
    @abstractmethod
    def save_config(self, rule_manager: RuleManager) -> None:
        """Save config to a target location(disk, db, etc)."""


class RDBRuleEngineConfigProducer(AbstractRuleEngineConfigProducer):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id

    def save_config(self, rule_manager: RuleManager) -> None:
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
            config_obj.config = rules_json
        except NoResultFound:
            new_config = RuleEngineConfig(
                label="production", config=rules_json, o_id=self.o_id
            )
            self.db.add(new_config)
        self.db.commit()


class YAMLRuleEngineConfigProducer(AbstractRuleEngineConfigProducer):
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path

    def save_config(self, rule_manager: RuleManager) -> None:
        YAMLRuleEngineConfigProducer.to_yaml(self.config_path, rule_manager)

    @staticmethod
    def to_yaml(file_path: str, rule_manager: RuleManager):
        open_fn = open
        if file_path.startswith("s3://"):
            import s3fs

            s3 = s3fs.S3FileSystem()
            open_fn = s3.open

        all_rules = rule_manager.load_all_rules()
        rules_json = [RuleConverter.to_json(r) for r in all_rules]
        full_rule_config = {"Rules": rules_json}
        yaml = ruamel.yaml.YAML()
        yaml.indent(offset=2, sequence=4)
        with open_fn(file_path, "w") as yaml_f:
            scalarstring.walk_tree(full_rule_config)
            yaml.dump(full_rule_config, yaml_f)


class RDBRuleManager(RuleManager):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id

    def _save_rule(self, rule: RuleModel) -> None:
        if rule.r_id is None:
            rule.o_id = self.o_id
            self.db.add(rule)
        self.db.commit()

    def get_rule_revision_list(
        self, rule: Rule, return_dates=False
    ) -> List[RuleRevision]:
        revisions = (
            self.db.query(
                RuleHistory.version, RuleHistory.changed, RuleHistory.created_at
            )
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

    def load_rule(
        self, rule_id: str, revision_number: Optional[str] = None
    ) -> RuleModel:
        if revision_number is None:
            latest_records = self.db.get(RuleModel, rule_id)
        else:
            latest_records = (
                self.db.query(RuleHistory)
                .filter(
                    RuleHistory.r_id == rule_id, RuleHistory.version == revision_number
                )
                .order_by(RuleHistory.version)
                .one()
            )
        return latest_records

    def load_all_rules(self) -> List[RuleModel]:
        org = self.db.get(Organisation, self.o_id)
        return org.rules


RULE_MANAGERS = {
    "RDBRuleManager": RDBRuleManager,
}


class RuleManagerFactory:
    @staticmethod
    def get_rule_manager(rule_manager_type: str, **kwargs):
        return RULE_MANAGERS[rule_manager_type](**kwargs)
