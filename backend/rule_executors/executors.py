from abc import ABC, abstractmethod
from core.rule_engine import RuleEngineFactory


class AbstractRuleExecutor(ABC):
    def __init__(self):
        self.rule_engine = None
        self._current_rule_version = None

    @abstractmethod
    def _check_rule_config_is_fresh(self):
        """Ensure the rule config is fresh."""

    def evaluate_rules(self, eval_object):
        self._check_rule_config_is_fresh()
        eval_result = self.rule_engine(eval_object)
        return eval_result


class LocalRuleExecutorSQL(AbstractRuleExecutor):
    def __init__(self, db, o_id):
        self.db = db
        self.o_id = o_id
        super().__init__()

    def _check_rule_config_is_fresh(self):
        from models.backend_core import RuleEngineConfig

        latest_record_version, latest_config = (
            self.db.query(RuleEngineConfig.version, RuleEngineConfig.config).where(
                RuleEngineConfig.label == "production",
                RuleEngineConfig.o_id == self.o_id,
            )
        ).one()
        if latest_record_version != self._current_rule_version:
            self._current_rule_version = latest_record_version
            self.rule_engine = RuleEngineFactory.from_json(latest_config)
