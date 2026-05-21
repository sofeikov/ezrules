from typing import Any

from ezrules.backend.rule_executors import executors
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.models.backend_core import Organisation, RuleEngineConfig, UserListHistory


class FakeRuleEngine:
    def __init__(self, outcome: str):
        self.outcome = outcome

    def get_rule_stats(self) -> set[str]:
        return set()

    def __call__(self, _event_data: dict, stats: dict[str, Any] | None = None) -> dict[str, Any]:
        del stats
        return {
            "rule_results": {1: self.outcome},
            "all_rule_results": {1: self.outcome},
            "outcome_counters": {self.outcome: 1},
            "outcome_set": [self.outcome],
        }


def test_rule_executor_reuses_compiled_engine_across_instances(session, monkeypatch):
    org = session.query(Organisation).one()
    session.add(
        RuleEngineConfig(
            label="production",
            version=1,
            config=[{"r_id": 1, "rid": "cached", "description": "Cached", "logic": "return !HOLD"}],
            o_id=int(org.o_id),
        )
    )
    session.commit()
    compile_calls: list[list[dict[str, Any]]] = []
    executors.reset_rule_engine_cache()
    monkeypatch.setattr(executors.app_settings, "TESTING", False)

    def fake_from_json(config, **_kwargs):
        compile_calls.append(config)
        return FakeRuleEngine("HOLD")

    monkeypatch.setattr(executors.RuleEngineFactory, "from_json", fake_from_json)

    first = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    second = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))

    assert first.evaluate_rules({})["outcome_counters"] == {"HOLD": 1}
    assert second.evaluate_rules({})["outcome_counters"] == {"HOLD": 1}
    assert len(compile_calls) == 1

    executors.reset_rule_engine_cache()


def test_rule_executor_recompiles_when_config_version_changes(session, monkeypatch):
    org = session.query(Organisation).one()
    config = RuleEngineConfig(
        label="production",
        version=1,
        config=[{"r_id": 1, "rid": "cached", "description": "Cached", "logic": "return !HOLD"}],
        o_id=int(org.o_id),
    )
    session.add(config)
    session.commit()
    compile_calls: list[list[dict[str, Any]]] = []
    executors.reset_rule_engine_cache()
    monkeypatch.setattr(executors.app_settings, "TESTING", False)

    def fake_from_json(config, **_kwargs):
        compile_calls.append(config)
        outcome = "CANCEL" if len(compile_calls) == 2 else "HOLD"
        return FakeRuleEngine(outcome)

    monkeypatch.setattr(executors.RuleEngineFactory, "from_json", fake_from_json)

    first = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    assert first.evaluate_rules({})["outcome_counters"] == {"HOLD": 1}

    config.version = 2
    config.config = [{"r_id": 1, "rid": "cached", "description": "Cached", "logic": "return !CANCEL"}]
    session.commit()

    second = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    assert second.evaluate_rules({})["outcome_counters"] == {"CANCEL": 1}
    assert len(compile_calls) == 2

    executors.reset_rule_engine_cache()


def test_rule_executor_recompiles_list_backed_rules_when_user_lists_change(session, monkeypatch):
    org = session.query(Organisation).one()
    session.add(
        RuleEngineConfig(
            label="production",
            version=1,
            config=[
                {
                    "r_id": 1,
                    "rid": "cached-list",
                    "description": "Cached list",
                    "logic": "if $merchant_id in @WatchlistMerchants:\n    return !HOLD\nreturn None",
                }
            ],
            o_id=int(org.o_id),
        )
    )
    session.commit()
    compile_calls: list[list[dict[str, Any]]] = []
    executors.reset_rule_engine_cache()
    monkeypatch.setattr(executors.app_settings, "TESTING", False)

    def fake_from_json(config, **_kwargs):
        compile_calls.append(config)
        outcome = "CANCEL" if len(compile_calls) == 2 else "HOLD"
        return FakeRuleEngine(outcome)

    monkeypatch.setattr(executors.RuleEngineFactory, "from_json", fake_from_json)

    first = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    assert first.evaluate_rules({})["outcome_counters"] == {"HOLD": 1}

    session.add(
        UserListHistory(
            ul_id=1,
            list_name="WatchlistMerchants",
            action="entry_added",
            o_id=int(org.o_id),
            details="Added entry",
        )
    )
    session.commit()

    second = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id))
    assert second.evaluate_rules({})["outcome_counters"] == {"CANCEL": 1}
    assert len(compile_calls) == 2

    executors.reset_rule_engine_cache()


def test_rule_executor_recompiles_when_config_row_is_recreated_with_same_version(session, monkeypatch):
    org = session.query(Organisation).one()
    config = RuleEngineConfig(
        label="allowlist",
        version=1,
        config=[{"r_id": 1, "rid": "cached", "description": "Cached", "logic": "return !HOLD"}],
        o_id=int(org.o_id),
    )
    session.add(config)
    session.commit()
    compile_calls: list[list[dict[str, Any]]] = []
    executors.reset_rule_engine_cache()
    monkeypatch.setattr(executors.app_settings, "TESTING", False)

    def fake_from_json(config, **_kwargs):
        compile_calls.append(config)
        outcome = "CANCEL" if "CANCEL" in str(config[0]["logic"]) else "HOLD"
        return FakeRuleEngine(outcome)

    monkeypatch.setattr(executors.RuleEngineFactory, "from_json", fake_from_json)

    first = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id), label="allowlist")
    assert first.evaluate_rules({})["outcome_counters"] == {"HOLD": 1}

    session.delete(config)
    session.commit()
    session.add(
        RuleEngineConfig(
            label="allowlist",
            version=1,
            config=[{"r_id": 1, "rid": "cached", "description": "Cached", "logic": "return !CANCEL"}],
            o_id=int(org.o_id),
        )
    )
    session.commit()

    second = LocalRuleExecutorSQL(db=session, o_id=int(org.o_id), label="allowlist")
    assert second.evaluate_rules({})["outcome_counters"] == {"CANCEL": 1}
    assert len(compile_calls) == 2

    executors.reset_rule_engine_cache()
