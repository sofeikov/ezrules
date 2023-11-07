import abc

from core.helpers import LockRecord
from core.rule import Rule
from datetime import timedelta
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, TTLAttribute
from typing import Optional, Tuple
from datetime import datetime, timezone
from models.backend_core import RuleEditLock


class RuleStorageLocker(abc.ABC):
    @abc.abstractmethod
    def lock_storage(self, rule: Rule, locked_by: str) -> Tuple[bool, LockRecord]:
        """Lock storage for a specific rule."""

    @abc.abstractmethod
    def release_storage(self, rule: Rule) -> None:
        """Release storage for a specific rule."""

    @abc.abstractmethod
    def is_record_locked(self, rule: Rule) -> Optional[LockRecord]:
        """Check if the rule is locked."""


class RelationalDBRuleLocker(RuleStorageLocker):
    def __init__(self, db):
        self.db = db

    def lock_storage(self, rule: Rule, locked_by: str) -> Tuple[bool, LockRecord]:
        lock_record = self.is_record_locked(rule)
        if lock_record is None:
            lock = RuleEditLock(
                rid=rule.rid,
                locked_by=locked_by,
                expires_on=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            self.db.add(lock)
            self.db.commit()
            return True, lock.to_lock_record()

        return False, lock_record

    def release_storage(self, rule: Rule) -> None:
        self.db.delete(self.db.get(RuleEditLock, rule.rid))
        self.db.commit()

    def is_record_locked(self, rule: Rule) -> Optional[LockRecord]:
        lock_record = self.db.get(RuleEditLock, rule.rid)
        if lock_record is None:
            return
        if lock_record.expires_on < datetime.utcnow():
            self.release_storage(rule)
            return
        return lock_record


class DynamoDBStorageLocker(RuleStorageLocker):
    class DBLockRecord(Model):
        class Meta:
            table_name = None
            region = "eu-west-1"

        rid = UnicodeAttribute(hash_key=True)
        locked_by = UnicodeAttribute(default="admin")
        expires_on = TTLAttribute()

        def to_lock_record(self) -> LockRecord:
            return LockRecord(
                rid=self.rid,
                locked_by=self.locked_by,
                expires_on=self.expires_on,
            )

    def __init__(self, table_name: str):
        self.DBLockRecord.Meta.table_name = table_name

    def lock_storage(self, rule: Rule, locked_by: str) -> Tuple[bool, LockRecord]:
        current_lock = self.is_record_locked(rule)
        if current_lock is None:
            db_lock_item = self.DBLockRecord(
                rid=rule.rid, expires_on=timedelta(hours=1), locked_by=locked_by
            )
            db_lock_item.save()
            return True, db_lock_item.to_lock_record()

        return False, current_lock

    def release_storage(self, rule: Rule) -> None:
        try:
            self.DBLockRecord.get(rule.rid).delete()
        except Model.DoesNotExist:
            pass

    def is_record_locked(self, rule: Rule) -> Optional[LockRecord]:
        try:
            db_lock_item = self.DBLockRecord.get(rule.rid)
            if db_lock_item.expires_on < datetime.now(timezone.utc):
                self.release_storage(rule)
                return
            return db_lock_item.to_lock_record()
        except Model.DoesNotExist:
            return
