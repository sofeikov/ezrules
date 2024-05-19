from abc import ABC, abstractmethod
from core.rule import Rule, RuleFactory, RuleConverter
from typing import Optional, List, Union, Tuple
from pathlib import Path
import os
import hashlib
import json
from ruamel.yaml import scalarstring
from datetime import datetime
import ruamel
import yaml
import operator
from collections import namedtuple
from sqlalchemy import func, distinct

from models.backend_core import (
    RuleEngineConfig,
    Rule as RuleModel,
    Organisation,
    RuleHistory,
)

RuleRevision = namedtuple("RuleRevision", ["revision_number", "created"])


class UnableToLockStorageException(Exception):
    """Generic exception for when it is impossible to lock a storage."""

    pass


class RuleDoesNotExistInTheStorage(Exception):
    """Generic exception thrown when the requested rule does not exist in the storage."""

    pass


def calculate_md5(input_string: str) -> str:
    """
    Return md5 hash of the given string.

    :param input_string: input string
    :return: md5 hash as string.
    """
    md5_hash = hashlib.md5(input_string.encode("utf-8")).hexdigest()
    return md5_hash


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

    def load_rules(self, rules_id: List[str]) -> List[Rule]:
        """
        Load the latest revisions of the given rules. It is a simple wrapper around :meth:`load_rule`

        :param rules_id:
        :return:
        """
        res = []
        for rid in rules_id:
            new_rule = self.load_rule(rid, revision_number=None)
            res.append(new_rule)
        return res

    @abstractmethod
    def load_all_rules(self) -> List[Rule]:
        """Storage specific mechanism to load all available rules."""


class AbstractRuleEngineConfigProducer(ABC):
    @abstractmethod
    def save_config(self, rule_manager: RuleManager) -> None:
        """Save config to a target location(disk, db, etc)."""


class RDBRuleEngineConfigProducer(AbstractRuleEngineConfigProducer):
    def __init__(self, db):
        self.db = db

    def save_config(self, rule_manager: RuleManager) -> None:
        all_rules = rule_manager.load_all_rules()
        all_rules = [RuleFactory.from_json(r.__dict__) for r in all_rules]
        rules_json = [RuleConverter.to_json(r) for r in all_rules]
        new_config = RuleEngineConfig(label="production", config=rules_json)
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


class FSRuleManager(RuleManager):
    """
    Rule manager that uses a local file system for keeping rule records. It is intended for local debugging and \
    illustrative purposes only and must never be used for any production deployments.
    """

    def __init__(self, fs_path: Union[str, Path]) -> None:
        """
        Initialise the class.

        :param fs_path: specify the location where the rule records will be kept. The process running the manager \
        must have write/read access to the target file system.
        """
        self.fs_path = Path(fs_path)
        self.fs_path.mkdir(parents=True, exist_ok=True)
        self._lock_fn = self.fs_path / "lock"
        self.manifest_fn = self.fs_path / "manifest.json"
        if not self.manifest_fn.exists():
            with open(self.manifest_fn, "w") as f:
                json.dump({}, f)

    def lock_storage(self):
        """Lock file system. Create a special file that indicates that an update is in progress."""
        if self._lock_fn.exists():
            raise UnableToLockStorageException(
                f"File {str(self._lock_fn)} exists. Lock has not been released."
            )
        open(self._lock_fn, "w").close()

    def release_storage(self):
        """Delete the lock indicator file."""
        os.remove(self._lock_fn)

    def __get_rule_folder_hash(
        self, rule_or_rid: Union[Rule, str]
    ) -> Tuple[Union[str, Path], str]:
        """
        Having an instance of :class:`core.rule_updater.RuleManager` or its id, get `pathlib.Path` for rule storages \
        and its md5 representation.

        :param rule_or_rid: :class:`core.rule_updater.RuleManager` or its string ID
        :return: Tuple with path and md5
        """
        if not isinstance(rule_or_rid, str):
            rule_or_rid = rule_or_rid.rid
        rid_hash = calculate_md5(rule_or_rid)
        rule_folder = self.fs_path / rid_hash
        return rule_folder, rid_hash

    def _save_rule(self, rule: Rule) -> None:
        """
        Save rule to disk. The rule configs are saved as YAML files.

        :param rule: instance of `core.rule_updater.RuleManager`
        :return:
        """
        rule_folder, rid_hash = self.__get_rule_folder_hash(rule)
        rule_folder.mkdir(exist_ok=True, parents=True)
        this_revision = 1
        revisions = self.get_rule_revision_list(rule)
        if revisions:
            this_revision = (
                max(
                    revisions, key=operator.attrgetter("revision_number")
                ).revision_number
                + 1
            )
        this_version_folder = rule_folder / str(this_revision)
        this_version_folder.mkdir(exist_ok=True, parents=True)
        rule_fn = this_version_folder / "rule.yaml"
        yaml = ruamel.yaml.YAML()
        yaml.indent(offset=2)
        with open(rule_fn, "w") as yaml_f:
            d = RuleConverter.to_json(rule)
            scalarstring.walk_tree(d)
            yaml.dump(d, yaml_f)
        if self.manifest_fn.exists():
            with open(self.manifest_fn, "r") as f:
                manifest = json.load(f)
        else:
            manifest = {}
        manifest[rule.rid] = rid_hash
        with open(self.manifest_fn, "w") as json_f:
            json.dump(manifest, json_f, indent=4)

    def get_rule_revision_list(
        self, rule: str, return_dates=False
    ) -> List[RuleRevision]:
        rule_folder, _ = self.__get_rule_folder_hash(rule)
        revision_list = sorted(
            [
                int(item.parts[-1])
                for item in rule_folder.glob("*")
                if item.is_dir() and item.parts[-1].isdigit()
            ]
        )
        return [
            RuleRevision(revision_number=r, created=datetime.now())
            for r in revision_list
        ]

    def load_rule(self, rule_id: str, revision_number: Optional[str] = None) -> Rule:
        """
        Load the latest version of the rule from the disk.

        :param rule_id: instance of `core.rule_updater.RuleManager`
        :param revision_number: rule revision number.
        :return:
        """
        rule_folder, _ = self.__get_rule_folder_hash(rule_id)
        if revision_number:
            rule_folder = rule_folder / str(revision_number)
        else:
            rule_folder = rule_folder / str(
                max(
                    self.get_rule_revision_list(rule_id),
                    key=operator.attrgetter("revision_number"),
                ).revision_number
            )
        rule_path = rule_folder / "rule.yaml"
        if not rule_path.exists():
            raise RuleDoesNotExistInTheStorage(
                f"Rule {rule_id} is not found at {rule_path}"
            )
        with open(rule_path) as f:
            rule_config = yaml.safe_load(f)
        return RuleFactory.from_json(rule_config)

    def load_all_rules(self) -> List[Rule]:
        self.lock_storage()
        with open(self.manifest_fn) as f:
            rules_id = list(json.load(f).keys())
        print(rules_id)
        ret_rules = [self.load_rule(rid) for rid in rules_id]
        self.release_storage()
        return ret_rules


class DynamoDBRuleManager(RuleManager):
    """Rule manager that uses AWS DynamoDB as storage backend. This implementation is stable enough to be used in
    production environment.
    """

    def __init__(self, table_name: str):
        """
        Instantiate object.

        :param table_name: the name of the DynamoDB table to be used. See class description for required table format.
        """
        import boto3

        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)

    def _save_rule(self, rule: Rule) -> None:
        revisions = self.get_rule_revision_list(rule)
        this_revision = 1
        if revisions:
            this_revision = (
                max(
                    revisions, key=operator.attrgetter("revision_number")
                ).revision_number
                + 1
            )
        self._save_rule_with_revision(rule, this_revision)

    def _save_rule_with_revision(self, rule: Rule, revision: int):
        rule_json = RuleConverter.to_json(rule)
        self.table.put_item(
            Item={
                **rule_json,
                "revision": revision,
                "created": int(datetime.now().timestamp()),
            }
        )

    def get_rule_revision_list(
        self, rule: Union[str, Rule], return_dates=False
    ) -> List[RuleRevision]:
        from boto3.dynamodb.conditions import Key

        rule_id = rule
        if isinstance(rule_id, Rule):
            rule_id = rule.rid
        response = self.table.query(KeyConditionExpression=Key("rid").eq(rule_id))
        items = response["Items"]
        all_revisions = sorted(
            [
                RuleRevision(
                    revision_number=int(item["revision"]),
                    created=datetime.fromtimestamp(item["created"]),
                )
                for item in items
            ],
            key=operator.attrgetter("revision_number"),
        )
        return all_revisions

    def load_rule(
        self, rule_id: str, revision_number: Optional[str] = None
    ) -> Optional[Rule]:
        if not revision_number:
            # Extract the latest revision number
            revision_resp = self.table.query(
                KeyConditions={
                    "rid": {
                        "AttributeValueList": [rule_id],
                        "ComparisonOperator": "EQ",
                    },
                },
                Select="SPECIFIC_ATTRIBUTES",
                ProjectionExpression="revision",
            )
            revision_number = max(
                [int(item["revision"]) for item in revision_resp["Items"]]
            )
        response = self.table.query(
            KeyConditions={
                "rid": {"AttributeValueList": [rule_id], "ComparisonOperator": "EQ"},
                "revision": {
                    "AttributeValueList": [revision_number],
                    "ComparisonOperator": "EQ",
                },
            }
        )
        items = response["Items"]
        if items:
            return RuleFactory.from_json(items[0])
        return None

    def load_all_rules(self) -> List[Rule]:
        response = self.table.scan()
        items = response["Items"]
        max_versions = {}
        for item in items:
            rid = item["rid"]
            if rid not in max_versions:
                max_versions[rid] = item["revision"]
            else:
                max_versions[rid] = max(max_versions[rid], item["revision"])
        items_latest = []
        for item in items:
            rid = item["rid"]
            if item["revision"] == max_versions[rid]:
                items_latest.append(item)

        ret_rules = [RuleFactory.from_json(item) for item in items_latest]
        return ret_rules


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
                created = revisions[ind-1].changed
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
    "FSRuleManager": FSRuleManager,
    "DynamoDBRuleManager": DynamoDBRuleManager,
    "RDBRuleManager": RDBRuleManager,
}


class RuleManagerFactory:
    @staticmethod
    def get_rule_manager(rule_manager_type: str, **kwargs):
        return RULE_MANAGERS[rule_manager_type](**kwargs)


if __name__ == "__main__":
    # fsrm = DynamoDBRuleManager("ezrules-rules-dev")
    fsrm = FSRuleManager("/Users/sofeikov/Downloads/ezrulesdb")
    with open("rule-config.yaml", "r") as fp:
        config = yaml.safe_load(fp)
    this_rules_config = config["Rules"]
    for rule_config in this_rules_config:
        this_rule = RuleFactory.from_json(rule_config)
        fsrm.save_rule(this_rule)

    print("loaded rule", fsrm.load_rule("[NA:049]"))

    print("all loaded rules", fsrm.load_all_rules())
