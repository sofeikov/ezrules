from abc import ABC, abstractmethod
from sqlalchemy import desc
from backend.rule_executors.utils import ensure_latest_etag
from core.rule_engine import RuleEngineFactory


class AbstractRuleExecutor(ABC):
    def __init__(self):
        self.rule_engine = None
        self._current_rule_version = None
        self._check_rule_config_is_fresh()

    @abstractmethod
    def _check_rule_config_is_fresh(self):
        """Ensure the rule config is fresh."""

    def evaluate_rules(self, eval_object):
        self._check_rule_config_is_fresh()
        eval_result = self.rule_engine(eval_object)
        return eval_result

    def __repr__(self):
        return "Abstract rule executor"


class LocalRuleExecutorS3Config(AbstractRuleExecutor):
    def __init__(self, rule_engine_yaml_path: str):
        super().__init__()
        self._rule_engine_yaml_path = rule_engine_yaml_path

    def _check_rule_config_is_fresh(self):
        new_rule_engine, self._current_rule_version = ensure_latest_etag(
            self._rule_engine_yaml_path, self._current_rule_version
        )
        self.rule_engine = new_rule_engine if new_rule_engine else self.rule_engine


class LocalRuleExecutorSQL(AbstractRuleExecutor):
    def __init__(self, db):
        self.db = db
        super().__init__()

    def _check_rule_config_is_fresh(self):
        from models.backend_core import RuleEngineConfig

        latest_record = (
            self.db.query(RuleEngineConfig).order_by(desc(RuleEngineConfig.id)).first()
        )
        if latest_record.id != self._current_rule_version:
            self._current_rule_version = latest_record.id
            self.rule_engine = RuleEngineFactory.from_json(latest_record.config)

    def __repr__(self):
        return f"{self.db.bind}"
