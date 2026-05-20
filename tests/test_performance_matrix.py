from pathlib import Path

import pytest

from ezrules.performance.events import build_event_data
from ezrules.performance.engine import build_rule_engine, time_rule_engine
from ezrules.performance.matrix import load_scenario, render_plan_markdown
from ezrules.performance.runner import _percentile, _request_count


def test_load_scenario_expands_multi_org_matrix(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: test-matrix
description: test
url: http://example.test
output_dir: artifacts/performance
organisations:
  - name: org-a
    api_key_env: ORG_A_KEY
    weight: 2
  - name: org-b
    api_key_env: ORG_B_KEY
rule_counts: [10, 50]
execution_modes: [all_matches, first_match]
match_profiles: [low_risk, high_risk]
rule_complexities: [simple]
workload:
  - name: smoke
    target_rps: 5
    duration_seconds: 30
    concurrency: 5
thresholds:
  max_failure_rate: 0.01
  max_p95_ms: 250
  max_p99_ms: 750
""",
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_path)

    assert [org.name for org in scenario.organisations] == ["org-a", "org-b"]
    assert scenario.organisations[0].weight == 2
    assert len(scenario.rows()) == 8
    assert scenario.thresholds.max_p95_ms == 250


def test_render_plan_markdown_names_required_target_setup(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: plan-test
description: docs
organisations:
  - name: org-a
    api_key_env: ORG_A_KEY
rule_counts: [0]
execution_modes: [all_matches]
match_profiles: [low_risk]
rule_complexities: [simple]
workload:
  - name: smoke
    target_rps: 1
    duration_seconds: 1
    concurrency: 1
""",
        encoding="utf-8",
    )
    scenario = load_scenario(scenario_path)

    markdown = render_plan_markdown(scenario)

    assert "Required Target Setup" in markdown
    assert "main_rule_execution_mode" in markdown
    assert "API keys are read from environment variables" in markdown


def test_event_profiles_are_deterministic_and_distinct():
    low_risk = build_event_data(match_profile="low_risk", seed=123)
    low_risk_again = build_event_data(match_profile="low_risk", seed=123)
    high_risk = build_event_data(match_profile="high_risk", seed=123)

    assert low_risk == low_risk_again
    assert low_risk["amount"] != high_risk["amount"]
    assert high_risk["email_domain"] == "mailinator.com"
    assert high_risk["customer"]["profile"]["age"] == 37
    assert high_risk["sender"]["device"]["trust_score"] == high_risk["device_trust_score"]


def test_unknown_event_profile_fails():
    with pytest.raises(ValueError, match="Unknown match profile"):
        build_event_data(match_profile="missing", seed=1)


def test_runner_math_helpers():
    assert _request_count(2.5, 10) == 25
    assert _percentile([1, 2, 3, 4], 50) == 2.5
    assert _percentile([1, 2, 3, 4], 95) == 4


def test_build_rule_engine_supports_demo_lists():
    engine = build_rule_engine(rule_count=14, execution_mode="all_matches")
    result = engine(build_event_data(match_profile="high_risk", seed=42))

    assert result["all_rule_results"]


def test_time_rule_engine_returns_latency_percentiles():
    result = time_rule_engine(
        rule_count=3,
        execution_mode="first_match",
        match_profile="cross_border",
        iterations=5,
    )

    assert result.iterations == 5
    assert result.evaluations_per_second > 0
    assert result.latency_p95_ms >= result.latency_min_ms
