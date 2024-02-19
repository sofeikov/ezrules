from abc import ABC, abstractmethod

from core.rule_engine import RuleEngineFactory
from backend.rule_executors.utils import ensure_latest_etag


class AbstractRuleExecutor(ABC):
    @abstractmethod
    def evaluate_rules(self, eval_object):
        """Evaluate object"""


class LocalRuleExecutor(AbstractRuleExecutor):
    def __init__(self, rule_engine_yaml_path: str):
        self._rule_engine_yaml_path = rule_engine_yaml_path
        self._current_rule_version = None
        self.rule_engine = RuleEngineFactory.from_yaml(rule_engine_yaml_path)

    def _check_rule_config_is_fresh(self):
        new_rule_engine, self._current_rule_version = ensure_latest_etag(
            self._rule_engine_yaml_path, self._current_rule_version
        )
        self.rule_engine = new_rule_engine if new_rule_engine else self.rule_engine

    def evaluate_rules(self, eval_object):
        self._check_rule_config_is_fresh()
        eval_result = self.rule_engine(eval_object)
        return eval_result
