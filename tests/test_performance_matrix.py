from pathlib import Path

import pytest

from ezrules.performance.events import build_event_data
from ezrules.performance.engine import build_rule_engine, time_rule_engine
from ezrules.performance.graph import (
    LocalGraphSuiteConfig,
    _filtered_graph_rows,
    _graph_shape_slice,
    _graph_transaction_id_width,
    load_graph_scenario,
    render_graph_plan_markdown,
    render_local_graph_suite_markdown,
)
from ezrules.performance.local_api_suite import (
    LocalApiSuiteConfig,
    _suite_env,
    _filtered_rows,
    _scenario_slice,
    render_api_suite_markdown,
)
from ezrules.performance.matrix import load_scenario, render_plan_markdown
from ezrules.performance.runner import RowResult, _percentile, _request_count


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


def test_build_rule_engine_uses_requested_rule_complexity():
    engine = build_rule_engine(rule_count=3, execution_mode="all_matches", rule_complexity="simple")
    result = engine(build_event_data(match_profile="high_risk", seed=42))

    assert result["outcome_counters"] == {"REVIEW": 3}


def test_time_rule_engine_returns_latency_percentiles():
    result = time_rule_engine(
        rule_count=3,
        execution_mode="first_match",
        match_profile="cross_border",
        rule_complexity="simple",
        iterations=5,
    )

    assert result.iterations == 5
    assert result.evaluations_per_second > 0
    assert result.latency_p95_ms >= result.latency_min_ms


def test_api_suite_slices_scenario_to_actual_seeded_rule_count_and_mode(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: api-suite-test
description: api
organisations:
  - name: org-a
    api_key_env: ORG_A_KEY
rule_counts: [50, 250]
execution_modes: [all_matches, first_match]
match_profiles: [low_risk, payout]
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
    config = LocalApiSuiteConfig(
        run_id="test",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        seed_events=10,
    )

    sliced = _scenario_slice(
        scenario,
        config=config,
        rule_count=250,
        rule_complexity="simple",
        execution_mode="first_match",
    )

    assert sliced.url == "http://localhost:18888"
    assert sliced.rule_counts == (250,)
    assert sliced.execution_modes == ("first_match",)
    assert sliced.rule_complexities == ("simple",)
    assert len(sliced.rows()) == 2


def test_api_suite_normalizes_human_run_id_for_local_resources():
    config = LocalApiSuiteConfig(
        run_id="Local-Test",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        seed_events=10,
    )

    assert config.db_name == "ezrules_perf_suite_local_test"
    assert config.postgres_container == "ezrules-perf-postgres-local-test"


def test_api_suite_row_filter_applies_after_mode_slice(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: api-suite-filter
description: api
organisations:
  - name: org-a
    api_key_env: ORG_A_KEY
rule_counts: [50]
execution_modes: [all_matches]
match_profiles: [low_risk, payout]
rule_complexities: [simple]
workload:
  - name: rps-20
    target_rps: 20
    duration_seconds: 1
    concurrency: 1
  - name: rps-50
    target_rps: 50
    duration_seconds: 1
    concurrency: 1
""",
        encoding="utf-8",
    )
    scenario = load_scenario(scenario_path)

    rows = _filtered_rows(scenario, "profile-payout__complexity-simple__load-rps-50")

    assert len(rows) == 1
    assert rows[0].match_profile == "payout"
    assert rows[0].step.name == "rps-50"


def test_api_suite_report_mentions_no_access_log_and_artifacts(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: api-suite-report
description: api
organisations:
  - name: org-a
    api_key_env: ORG_A_KEY
rule_counts: [50]
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
    config = LocalApiSuiteConfig(
        run_id="report",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        seed_events=10,
    )
    result = RowResult(
        layer="api-ingestion",
        row_id="rules-50__mode-all_matches__profile-low_risk__complexity-simple__load-smoke",
        started_at="2026-05-21T00:00:00+00:00",
        completed_at="2026-05-21T00:00:01+00:00",
        planned_requests=1,
        ok=1,
        failed=0,
        failure_rate=0,
        achieved_rps=1,
        latency_min_ms=10,
        latency_p50_ms=10,
        latency_p95_ms=10,
        latency_p99_ms=10,
        latency_max_ms=10,
        status_counts={"200": 1},
        first_error=None,
        breached_thresholds=[],
    )

    markdown = render_api_suite_markdown(
        scenario=scenario,
        config=config,
        results=[result],
        samples_path=tmp_path / "samples.csv",
        api_log_path=tmp_path / "api.log",
    )

    assert "API access log | `disabled`" in markdown
    assert "samples.csv" in markdown
    assert "rules-50__mode-all_matches" in markdown


def test_load_graph_scenario_expands_shape_hop_and_workload_matrix(tmp_path: Path):
    scenario_path = tmp_path / "graph.yaml"
    scenario_path.write_text(
        """
name: graph-test
description: graph docs
url: http://example.test
output_dir: artifacts/performance
graph_shapes:
  - name: small
    event_count: 100
    entities_per_event: 4
    shared_entity_count: 25
    entity_type_count: 3
  - name: dense
    event_count: 500
    entities_per_event: 8
    shared_entity_count: 40
max_events: [10, 25]
max_hops: [1, 3]
workload:
  - name: smoke
    target_rps: 5
    duration_seconds: 10
    concurrency: 5
  - name: ramp
    target_rps: 25
    duration_seconds: 20
    warmup_seconds: 5
    concurrency: 25
thresholds:
  max_failure_rate: 0.01
  max_p95_ms: 300
  max_p99_ms: 900
""",
        encoding="utf-8",
    )

    scenario = load_graph_scenario(scenario_path)

    assert scenario.url == "http://example.test"
    assert len(scenario.rows()) == 16
    assert scenario.graph_shapes[1].entity_type_count == 4
    assert scenario.thresholds.max_p95_ms == 300


def test_render_graph_plan_markdown_mentions_live_and_local_modes(tmp_path: Path):
    scenario_path = tmp_path / "graph-plan.yaml"
    scenario_path.write_text(
        """
name: graph-plan
description: graph docs
graph_shapes:
  - name: small
    event_count: 100
    entities_per_event: 4
    shared_entity_count: 25
max_events: [10]
max_hops: [3]
workload:
  - name: smoke
    target_rps: 5
    duration_seconds: 10
    concurrency: 5
""",
        encoding="utf-8",
    )
    scenario = load_graph_scenario(scenario_path)

    markdown = render_graph_plan_markdown(scenario)

    assert "Graph Traversal Performance Matrix" in markdown
    assert "EZRULES_GRAPH_PERF_BEARER_TOKEN" in markdown
    assert "shape-small__events-100" in markdown


def test_graph_suite_slices_scenario_to_seeded_shape_and_filters_rows(tmp_path: Path):
    scenario_path = tmp_path / "graph-filter.yaml"
    scenario_path.write_text(
        """
name: graph-filter
description: graph
graph_shapes:
  - name: small
    event_count: 100
    entities_per_event: 4
    shared_entity_count: 25
  - name: large
    event_count: 1000
    entities_per_event: 6
    shared_entity_count: 100
max_events: [10, 50]
max_hops: [1, 3]
workload:
  - name: smoke
    target_rps: 5
    duration_seconds: 10
    concurrency: 5
""",
        encoding="utf-8",
    )
    scenario = load_graph_scenario(scenario_path)
    config = LocalGraphSuiteConfig(
        run_id="Graph-Test",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        root_decisions=10,
    )

    sliced = _graph_shape_slice(scenario, config=config, shape=scenario.graph_shapes[1])
    rows = _filtered_graph_rows(sliced, "max-events-50__hops-3")

    assert config.db_name == "ezrules_graph_perf_graph_test"
    assert sliced.url == "http://localhost:18888"
    assert sliced.graph_shapes[0].name == "large"
    assert len(rows) == 1
    assert rows[0].max_events == 50
    assert rows[0].max_hops == 3


def test_graph_suite_report_records_resource_limits(tmp_path: Path):
    scenario_path = tmp_path / "graph-report.yaml"
    scenario_path.write_text(
        """
name: graph-report
description: graph
graph_shapes:
  - name: small
    event_count: 100
    entities_per_event: 4
    shared_entity_count: 25
max_events: [10]
max_hops: [3]
workload:
  - name: smoke
    target_rps: 5
    duration_seconds: 10
    concurrency: 5
""",
        encoding="utf-8",
    )
    scenario = load_graph_scenario(scenario_path)
    config = LocalGraphSuiteConfig(
        run_id="report",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        root_decisions=10,
        postgres_cpus="2",
        postgres_memory="2g",
    )
    result = RowResult(
        layer="graph-api",
        row_id="shape-small__events-100__entities-4__shared-25__max-events-10__hops-3__load-smoke",
        started_at="2026-05-21T00:00:00+00:00",
        completed_at="2026-05-21T00:00:01+00:00",
        planned_requests=1,
        ok=1,
        failed=0,
        failure_rate=0,
        achieved_rps=1,
        latency_min_ms=10,
        latency_p50_ms=10,
        latency_p95_ms=10,
        latency_p99_ms=10,
        latency_max_ms=10,
        status_counts={"200": 1},
        first_error=None,
        breached_thresholds=[],
    )

    markdown = render_local_graph_suite_markdown(
        scenario=scenario,
        config=config,
        results=[result],
        samples_path=tmp_path / "samples.csv",
        api_log_path=tmp_path / "api.log",
    )

    assert "Postgres CPU limit | `2`" in markdown
    assert "Postgres memory limit | `2g`" in markdown
    assert "shape-small__events-100" in markdown


def test_graph_suite_exports_database_pool_settings():
    config = LocalGraphSuiteConfig(
        run_id="pool",
        api_port=18888,
        postgres_port=55432,
        redis_port=56379,
        workers=4,
        root_decisions=10,
        db_pool_size=25,
        db_max_overflow=50,
        db_pool_timeout_seconds=5,
    )

    env = _suite_env(config, testing=False)

    assert env["EZRULES_DB_POOL_SIZE"] == "25"
    assert env["EZRULES_DB_MAX_OVERFLOW"] == "50"
    assert env["EZRULES_DB_POOL_TIMEOUT_SECONDS"] == "5"


def test_graph_transaction_id_width_scales_past_millions():
    assert _graph_transaction_id_width(999_999) == 7
    assert _graph_transaction_id_width(10_000_000) == 8
