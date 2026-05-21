from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from ezrules.backend.features import FeatureResolver
from ezrules.core.rule_engine import RULE_EXECUTION_MODE_ALL_MATCHES, RuleEngineFactory
from ezrules.core.rule_helpers import UserListReferenceExtractor
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.settings import app_settings

_RULE_ENGINE_CACHE_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class RuleEngineCacheState:
    re_id: int
    config_version: int
    user_list_version: tuple[int, int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class RuleEngineCacheEntry:
    state: RuleEngineCacheState
    engine: Any
    depends_on_user_lists: bool


_RULE_ENGINE_CACHE: dict[tuple[int, str, str], RuleEngineCacheEntry] = {}


def reset_rule_engine_cache() -> None:
    """Clear compiled rule engines cached in the current worker process."""
    with _RULE_ENGINE_CACHE_LOCK:
        _RULE_ENGINE_CACHE.clear()


def _should_use_shared_rule_engine_cache() -> bool:
    return not bool(app_settings.TESTING)


class AbstractRuleExecutor(ABC):
    def __init__(self):
        self.rule_engine = None
        self._current_cache_state: RuleEngineCacheState | None = None
        self._current_depends_on_user_lists = False
        self._current_execution_mode = None

    @abstractmethod
    def _check_rule_config_is_fresh(self):
        """Ensure the rule config is fresh."""

    def get_rule_stats(self) -> set[str]:
        self._check_rule_config_is_fresh()
        if self.rule_engine is None:
            return set()
        return self.rule_engine.get_rule_stats()

    def evaluate_rules(self, eval_object, *, as_of: datetime | None = None, stats: dict[str, Any] | None = None):
        self._check_rule_config_is_fresh()
        if self.rule_engine is None:
            return {"outcome_counters": {}, "outcome_set": set(), "rule_results": {}}
        if stats is None and as_of is not None:
            stats = FeatureResolver(self.db, self.o_id).resolve(
                eval_object,
                as_of,
                self.rule_engine.get_rule_stats(),
            )
        if stats is None:
            stats = {}
        eval_result = self.rule_engine(eval_object, stats=stats)
        return eval_result


class LocalRuleExecutorSQL(AbstractRuleExecutor):
    def __init__(self, db, o_id, label: str = "production", execution_mode: str = RULE_EXECUTION_MODE_ALL_MATCHES):
        self.db = db
        self.o_id = o_id
        self.label = label
        self.execution_mode = execution_mode
        super().__init__()

    def _check_rule_config_is_fresh(self):
        from ezrules.models.backend_core import RuleEngineConfig

        cache_key = (int(self.o_id), str(self.label), str(self.execution_mode))
        try:
            latest_record = (
                self.db.query(RuleEngineConfig.re_id, RuleEngineConfig.version).where(
                    RuleEngineConfig.label == self.label,
                    RuleEngineConfig.o_id == self.o_id,
                )
            ).one()
        except NoResultFound:
            self.rule_engine = None
            self._current_cache_state = None
            self._current_depends_on_user_lists = False
            self._current_execution_mode = None
            with _RULE_ENGINE_CACHE_LOCK:
                _RULE_ENGINE_CACHE.pop(cache_key, None)
            return

        re_id = int(latest_record[0])
        latest_version = int(latest_record[1])
        user_list_version: tuple[int, int, int, int, int] | None = None

        if self._current_cache_state is not None and self.execution_mode == self._current_execution_mode:
            current_state = RuleEngineCacheState(re_id=re_id, config_version=latest_version)
            if self._current_depends_on_user_lists:
                user_list_version = self._get_user_list_cache_version()
                current_state = RuleEngineCacheState(
                    re_id=re_id,
                    config_version=latest_version,
                    user_list_version=user_list_version,
                )
            if current_state == self._current_cache_state:
                return

        cached = None
        if _should_use_shared_rule_engine_cache():
            with _RULE_ENGINE_CACHE_LOCK:
                cached = _RULE_ENGINE_CACHE.get(cache_key)

        if cached is not None:
            cache_state = RuleEngineCacheState(re_id=re_id, config_version=latest_version)
            if cached.depends_on_user_lists:
                if user_list_version is None:
                    user_list_version = self._get_user_list_cache_version()
                cache_state = RuleEngineCacheState(
                    re_id=re_id,
                    config_version=latest_version,
                    user_list_version=user_list_version,
                )
            if cached.state == cache_state:
                self._current_cache_state = cache_state
                self._current_depends_on_user_lists = cached.depends_on_user_lists
                self._current_execution_mode = self.execution_mode
                self.rule_engine = cached.engine
                return

            with _RULE_ENGINE_CACHE_LOCK:
                if _RULE_ENGINE_CACHE.get(cache_key) == cached:
                    _RULE_ENGINE_CACHE.pop(cache_key, None)

        latest_config = (
            self.db.query(RuleEngineConfig.config)
            .where(
                RuleEngineConfig.label == self.label,
                RuleEngineConfig.o_id == self.o_id,
            )
            .one()[0]
        )
        depends_on_user_lists = _rule_config_uses_user_lists(latest_config)
        if depends_on_user_lists and user_list_version is None:
            user_list_version = self._get_user_list_cache_version()
        cache_state = RuleEngineCacheState(
            re_id=re_id,
            config_version=latest_version,
            user_list_version=user_list_version if depends_on_user_lists else None,
        )
        rule_engine = RuleEngineFactory.from_json(
            latest_config,
            list_values_provider=PersistentUserListManager(self.db, self.o_id),
            execution_mode=self.execution_mode,
        )
        if _should_use_shared_rule_engine_cache():
            with _RULE_ENGINE_CACHE_LOCK:
                _RULE_ENGINE_CACHE[cache_key] = RuleEngineCacheEntry(
                    state=cache_state,
                    engine=rule_engine,
                    depends_on_user_lists=depends_on_user_lists,
                )

        self._current_cache_state = cache_state
        self._current_depends_on_user_lists = depends_on_user_lists
        self._current_execution_mode = self.execution_mode
        self.rule_engine = rule_engine

    def _get_user_list_cache_version(self) -> tuple[int, int, int, int, int]:
        from ezrules.models.backend_core import UserList, UserListEntry, UserListHistory

        list_count = select(func.count(UserList.ul_id)).where(UserList.o_id == self.o_id).scalar_subquery()
        list_max_id = (
            select(func.coalesce(func.max(UserList.ul_id), 0)).where(UserList.o_id == self.o_id).scalar_subquery()
        )
        entry_count = (
            select(func.count(UserListEntry.ule_id))
            .select_from(UserListEntry)
            .join(UserList, UserList.ul_id == UserListEntry.ul_id)
            .where(UserList.o_id == self.o_id)
            .scalar_subquery()
        )
        entry_max_id = (
            select(func.coalesce(func.max(UserListEntry.ule_id), 0))
            .select_from(UserListEntry)
            .join(UserList, UserList.ul_id == UserListEntry.ul_id)
            .where(UserList.o_id == self.o_id)
            .scalar_subquery()
        )
        history_max_id = (
            select(func.coalesce(func.max(UserListHistory.id), 0))
            .where(UserListHistory.o_id == self.o_id)
            .scalar_subquery()
        )
        version = self.db.query(list_count, list_max_id, entry_count, entry_max_id, history_max_id).one()
        return (
            int(version[0] or 0),
            int(version[1] or 0),
            int(version[2] or 0),
            int(version[3] or 0),
            int(version[4] or 0),
        )


def _rule_config_uses_user_lists(config: list[dict[str, Any]]) -> bool:
    extractor = UserListReferenceExtractor()
    for rule_config in config:
        logic = rule_config.get("logic")
        if isinstance(logic, str) and extractor.extract(logic):
            return True
    return False
