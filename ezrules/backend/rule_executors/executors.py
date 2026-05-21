from abc import ABC, abstractmethod
from datetime import datetime
from threading import Lock
from typing import Any

from sqlalchemy.exc import NoResultFound

from ezrules.backend.features import FeatureResolver
from ezrules.core.rule_engine import RULE_EXECUTION_MODE_ALL_MATCHES, RuleEngineFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.settings import app_settings

_RULE_ENGINE_CACHE_LOCK = Lock()
_RULE_ENGINE_CACHE: dict[tuple[int, str, str], tuple[int, Any]] = {}


def reset_rule_engine_cache() -> None:
    """Clear compiled rule engines cached in the current worker process."""
    with _RULE_ENGINE_CACHE_LOCK:
        _RULE_ENGINE_CACHE.clear()


def _should_use_shared_rule_engine_cache() -> bool:
    return not bool(app_settings.TESTING)


class AbstractRuleExecutor(ABC):
    def __init__(self):
        self.rule_engine = None
        self._current_rule_version = None
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

        try:
            latest_record_version = (
                self.db.query(RuleEngineConfig.version).where(
                    RuleEngineConfig.label == self.label,
                    RuleEngineConfig.o_id == self.o_id,
                )
            ).one()
        except NoResultFound:
            self.rule_engine = None
            self._current_rule_version = None
            self._current_execution_mode = None
            return

        latest_version = int(latest_record_version[0])
        cache_key = (int(self.o_id), str(self.label), str(self.execution_mode))

        if latest_version == self._current_rule_version and self.execution_mode == self._current_execution_mode:
            return

        cached = None
        if _should_use_shared_rule_engine_cache():
            with _RULE_ENGINE_CACHE_LOCK:
                cached = _RULE_ENGINE_CACHE.get(cache_key)

        if cached is not None and cached[0] == latest_version:
            self._current_rule_version = latest_version
            self._current_execution_mode = self.execution_mode
            self.rule_engine = cached[1]
            return

        latest_config = (
            self.db.query(RuleEngineConfig.config)
            .where(
                RuleEngineConfig.label == self.label,
                RuleEngineConfig.o_id == self.o_id,
            )
            .one()[0]
        )
        rule_engine = RuleEngineFactory.from_json(
            latest_config,
            list_values_provider=PersistentUserListManager(self.db, self.o_id),
            execution_mode=self.execution_mode,
        )
        if _should_use_shared_rule_engine_cache():
            with _RULE_ENGINE_CACHE_LOCK:
                _RULE_ENGINE_CACHE[cache_key] = (latest_version, rule_engine)

        self._current_rule_version = latest_version
        self._current_execution_mode = self.execution_mode
        self.rule_engine = rule_engine
