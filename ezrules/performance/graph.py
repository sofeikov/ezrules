from __future__ import annotations

import json
import math
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ezrules.performance.local_api_suite import (
    ResourceSampler,
    _cleanup_infra,
    _initialize_database,
    _psql,
    _reset_pg_stat_statements,
    _run,
    _start_api,
    _start_infra,
    _stop_process,
    _suite_env,
    _wait_for_api,
    default_run_id,
)
from ezrules.performance.matrix import Thresholds, WorkloadStep
from ezrules.performance.runner import RowResult, _format_latency, _percentile, _request_count


@dataclass(frozen=True, slots=True)
class GraphShape:
    """One seeded event/entity topology for traversal load tests."""

    name: str
    event_count: int
    entities_per_event: int
    shared_entity_count: int
    entity_type_count: int = 4


@dataclass(frozen=True, slots=True)
class GraphTraversalRow:
    """One graph endpoint load row."""

    row_id: str
    shape: GraphShape
    max_events: int
    max_hops: int
    step: WorkloadStep


@dataclass(frozen=True, slots=True)
class GraphScenario:
    """Loaded graph traversal performance scenario."""

    name: str
    description: str
    url: str
    graph_shapes: tuple[GraphShape, ...]
    max_events: tuple[int, ...]
    max_hops: tuple[int, ...]
    workload: tuple[WorkloadStep, ...]
    thresholds: Thresholds
    output_dir: Path

    def rows(self) -> list[GraphTraversalRow]:
        rows: list[GraphTraversalRow] = []
        for shape in self.graph_shapes:
            for max_event_count in self.max_events:
                for hop_count in self.max_hops:
                    for step in self.workload:
                        row_id = (
                            f"shape-{shape.name}__events-{shape.event_count}__entities-{shape.entities_per_event}__"
                            f"shared-{shape.shared_entity_count}__max-events-{max_event_count}__hops-{hop_count}__"
                            f"load-{step.name}"
                        )
                        rows.append(
                            GraphTraversalRow(
                                row_id=row_id,
                                shape=shape,
                                max_events=max_event_count,
                                max_hops=hop_count,
                                step=step,
                            )
                        )
        return rows

    def plan_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "thresholds": {
                "max_failure_rate": self.thresholds.max_failure_rate,
                "max_p95_ms": self.thresholds.max_p95_ms,
                "max_p99_ms": self.thresholds.max_p99_ms,
            },
            "graph_shapes": [asdict(shape) for shape in self.graph_shapes],
            "rows": [
                {
                    "row_id": row.row_id,
                    "shape": row.shape.name,
                    "event_count": row.shape.event_count,
                    "entities_per_event": row.shape.entities_per_event,
                    "shared_entity_count": row.shape.shared_entity_count,
                    "entity_type_count": row.shape.entity_type_count,
                    "max_events": row.max_events,
                    "max_hops": row.max_hops,
                    "target_rps": row.step.target_rps,
                    "duration_seconds": row.step.duration_seconds,
                    "warmup_seconds": row.step.warmup_seconds,
                    "concurrency": row.step.concurrency,
                }
                for row in self.rows()
            ],
        }


@dataclass(frozen=True, slots=True)
class GraphRequestResult:
    ok: bool
    status_code: int
    latency_ms: float
    evaluation_decision_id: int
    node_count: int | None = None
    edge_count: int | None = None
    event_count: int | None = None
    truncated: bool | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LocalGraphSuiteConfig:
    """Runtime settings for a disposable local graph traversal suite."""

    run_id: str
    api_port: int
    postgres_port: int
    redis_port: int
    workers: int
    root_decisions: int
    org_name: str = "graph-perf-org"
    admin_email: str = "graph-perf@example.com"
    admin_password: str = "admin"
    postgres_image: str = "postgres:16.0-alpine3.18"
    redis_image: str = "redis:7-alpine"
    postgres_cpus: str | None = None
    postgres_memory: str | None = None
    postgres_max_connections: int | None = None
    postgres_data_dir: Path | None = None
    redis_cpus: str | None = None
    redis_memory: str | None = None
    db_pool_size: int | None = None
    db_max_overflow: int | None = None
    db_pool_timeout_seconds: int | None = None
    continue_after_breach: bool = True
    no_access_log: bool = True
    cleanup: bool = True
    output_dir: Path | None = None
    row_filter: str | None = None

    @property
    def resource_id(self) -> str:
        normalized = "".join(character.lower() if character.isalnum() else "_" for character in self.run_id).strip("_")
        return normalized or "run"

    @property
    def docker_resource_id(self) -> str:
        return self.resource_id.replace("_", "-")

    @property
    def db_name(self) -> str:
        return f"ezrules_graph_perf_{self.resource_id}"

    @property
    def postgres_container(self) -> str:
        return f"ezrules-graph-postgres-{self.docker_resource_id}"

    @property
    def redis_container(self) -> str:
        return f"ezrules-graph-redis-{self.docker_resource_id}"

    @property
    def api_url(self) -> str:
        return f"http://localhost:{self.api_port}"

    @property
    def db_endpoint(self) -> str:
        return f"postgresql://postgres:root@localhost:{self.postgres_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        return f"redis://localhost:{self.redis_port}"


@dataclass(frozen=True, slots=True)
class LocalGraphSuiteArtifacts:
    json_path: Path
    markdown_path: Path
    samples_path: Path
    api_log_path: Path


def load_graph_scenario(path: str | Path) -> GraphScenario:
    scenario_path = Path(path)
    raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Graph scenario file must contain a YAML mapping.")

    thresholds_raw = raw.get("thresholds") or {}
    if not isinstance(thresholds_raw, dict):
        raise ValueError("thresholds must be a mapping when provided.")

    return GraphScenario(
        name=_required_str(raw, "name"),
        description=str(raw.get("description", "")).strip(),
        url=str(raw.get("url", "http://localhost:8888")).rstrip("/"),
        graph_shapes=tuple(_load_graph_shapes(raw.get("graph_shapes"))),
        max_events=tuple(_required_int_list(raw, "max_events")),
        max_hops=tuple(_required_int_list(raw, "max_hops")),
        workload=tuple(_load_workload(raw.get("workload"))),
        thresholds=Thresholds(
            max_failure_rate=float(thresholds_raw.get("max_failure_rate", 0.001)),
            max_p95_ms=float(thresholds_raw.get("max_p95_ms", 500.0)),
            max_p99_ms=float(thresholds_raw.get("max_p99_ms", 1000.0)),
        ),
        output_dir=Path(str(raw.get("output_dir", "artifacts/performance"))),
    )


def write_graph_plan_files(scenario: GraphScenario) -> tuple[Path, Path]:
    scenario.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = scenario.output_dir / f"{scenario.name}-graph-plan.json"
    markdown_path = scenario.output_dir / f"{scenario.name}-graph-plan.md"
    json_path.write_text(json.dumps(scenario.plan_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_graph_plan_markdown(scenario), encoding="utf-8")
    return json_path, markdown_path


def render_graph_plan_markdown(scenario: GraphScenario) -> str:
    lines = [
        f"# Graph Traversal Performance Matrix: {scenario.name}",
        "",
        scenario.description,
        "",
        "## Target",
        "",
        f"- URL: `{scenario.url}`",
        "- Live `graph-run` requires `EZRULES_GRAPH_PERF_BEARER_TOKEN` and `EZRULES_GRAPH_PERF_DECISION_IDS`.",
        "- Local `graph-api-suite` seeds connected event/entity rows in a disposable database.",
        "",
        "## Graph Shapes",
        "",
        "| Shape | Events | Entities / Event | Shared Entity Values | Entity Types |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for shape in scenario.graph_shapes:
        lines.append(
            f"| `{shape.name}` | {shape.event_count} | {shape.entities_per_event} | "
            f"{shape.shared_entity_count} | {shape.entity_type_count} |"
        )
    lines.extend(
        [
            "",
            "## Matrix Rows",
            "",
            "| Row | Max Events | Hops | RPS | Duration | Concurrency |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in scenario.rows():
        lines.append(
            f"| `{row.row_id}` | {row.max_events} | {row.max_hops} | {row.step.target_rps:g} | "
            f"{row.step.duration_seconds}s | {row.step.concurrency} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_graph_scenario(
    *,
    scenario: GraphScenario,
    rows: list[GraphTraversalRow],
    bearer_token: str,
    evaluation_decision_ids: list[int],
    continue_after_breach: bool = False,
) -> list[RowResult]:
    if not evaluation_decision_ids:
        raise ValueError("At least one evaluation decision id is required.")

    results: list[RowResult] = []
    for row in rows:
        print(f"Running {row.row_id} ...", flush=True)
        result = run_graph_row(
            scenario=scenario,
            row=row,
            bearer_token=bearer_token,
            evaluation_decision_ids=evaluation_decision_ids,
        )
        results.append(result)
        print(
            f"  ok={result.ok} failed={result.failed} rps={result.achieved_rps:.1f} "
            f"p95={_format_latency(result.latency_p95_ms)} breaches={','.join(result.breached_thresholds) or 'none'}",
            flush=True,
        )
        if result.breached_thresholds and not continue_after_breach:
            print("Stopping after first threshold breach. Use --continue-after-breach to run remaining rows.")
            break
    return results


def run_graph_row(
    *,
    scenario: GraphScenario,
    row: GraphTraversalRow,
    bearer_token: str,
    evaluation_decision_ids: list[int],
) -> RowResult:
    started = datetime.now(UTC)
    warmup_requests = _request_count(row.step.target_rps, row.step.warmup_seconds)
    measured_requests = _request_count(row.step.target_rps, row.step.duration_seconds)

    if warmup_requests:
        _send_graph_requests(
            scenario=scenario,
            row=row,
            bearer_token=bearer_token,
            evaluation_decision_ids=evaluation_decision_ids,
            request_count=warmup_requests,
            duration_seconds=row.step.warmup_seconds,
        )

    measure_start = time.perf_counter()
    request_results = _send_graph_requests(
        scenario=scenario,
        row=row,
        bearer_token=bearer_token,
        evaluation_decision_ids=evaluation_decision_ids,
        request_count=measured_requests,
        duration_seconds=row.step.duration_seconds,
    )
    elapsed = time.perf_counter() - measure_start
    completed = datetime.now(UTC)

    ok_results = [result for result in request_results if result.ok]
    latencies = sorted(result.latency_ms for result in ok_results)
    failed = len(request_results) - len(ok_results)
    status_counts: dict[str, int] = {}
    for result in request_results:
        key = str(result.status_code)
        status_counts[key] = status_counts.get(key, 0) + 1

    row_result = RowResult(
        layer="graph-api",
        row_id=row.row_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        planned_requests=measured_requests,
        ok=len(ok_results),
        failed=failed,
        failure_rate=failed / len(request_results) if request_results else 0.0,
        achieved_rps=len(ok_results) / elapsed if elapsed > 0 else 0.0,
        latency_min_ms=latencies[0] if latencies else None,
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
        latency_p99_ms=_percentile(latencies, 99),
        latency_max_ms=latencies[-1] if latencies else None,
        status_counts=status_counts,
        first_error=next((result.error for result in request_results if result.error), None),
        breached_thresholds=[],
    )
    return _with_graph_threshold_breaches(row_result, scenario)


def write_graph_result_files(scenario: GraphScenario, results: list[RowResult], *, layer: str) -> tuple[Path, Path]:
    scenario.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{scenario.name}-{layer}-{timestamp}"
    payload = {"scenario": scenario.plan_payload(), "results": [asdict(result) for result in results]}
    json_path = scenario.output_dir / f"{stem}.json"
    markdown_path = scenario.output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_graph_results_markdown(scenario, results, layer=layer), encoding="utf-8")
    return json_path, markdown_path


def render_graph_results_markdown(scenario: GraphScenario, results: list[RowResult], *, layer: str) -> str:
    lines = [
        f"# Graph Traversal Performance Results: {scenario.name}",
        "",
        f"Layer: `{layer}`",
        f"Target: `{scenario.url}`",
        "",
        "| Row | OK | Failed | Failure Rate | RPS | p50 | p95 | p99 | Breaches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(
            f"| `{result.row_id}` | {result.ok} | {result.failed} | {result.failure_rate:.4f} | "
            f"{result.achieved_rps:.1f} | {_format_latency(result.latency_p50_ms)} | "
            f"{_format_latency(result.latency_p95_ms)} | {_format_latency(result.latency_p99_ms)} | "
            f"{', '.join(result.breached_thresholds) or 'none'} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_local_graph_suite(scenario: GraphScenario, config: LocalGraphSuiteConfig) -> LocalGraphSuiteArtifacts:
    output_dir = config.output_dir or scenario.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    api_log_path = output_dir / f"{scenario.name}-graph-api-suite-{config.run_id}-api.log"
    samples_path = output_dir / f"{scenario.name}-graph-api-suite-{config.run_id}-samples.csv"

    results: list[RowResult] = []
    api_process: subprocess.Popen | None = None
    sampler: ResourceSampler | None = None

    try:
        _start_infra(config)  # type: ignore[arg-type]
        _initialize_database(config)  # type: ignore[arg-type]
        _bootstrap_graph_org(config)
        sampler = ResourceSampler(samples_path=samples_path, config=config)  # type: ignore[arg-type]
        sampler.start()

        for shape in scenario.graph_shapes:
            _seed_graph_shape(config, shape)
            decision_ids = _graph_decision_ids(config, config.root_decisions)
            if not decision_ids:
                raise RuntimeError(f"No graph decision ids were seeded for shape {shape.name}.")
            _reset_pg_stat_statements(config)  # type: ignore[arg-type]

            _stop_process(api_process)
            api_process = _start_api(config, api_log_path)  # type: ignore[arg-type]
            _wait_for_api(config.api_url)
            bearer_token = _login(config)

            shape_scenario = _graph_shape_slice(scenario, config=config, shape=shape)
            rows = _filtered_graph_rows(shape_scenario, config.row_filter)
            if rows:
                results.extend(
                    run_graph_scenario(
                        scenario=shape_scenario,
                        rows=rows,
                        bearer_token=bearer_token,
                        evaluation_decision_ids=decision_ids,
                        continue_after_breach=config.continue_after_breach,
                    )
                )

        json_path, markdown_path = write_local_graph_suite_files(
            scenario=scenario,
            config=config,
            results=results,
            samples_path=samples_path,
            api_log_path=api_log_path,
            output_dir=output_dir,
        )
        return LocalGraphSuiteArtifacts(
            json_path=json_path,
            markdown_path=markdown_path,
            samples_path=samples_path,
            api_log_path=api_log_path,
        )
    finally:
        if sampler is not None:
            sampler.stop()
        _stop_process(api_process)
        if config.cleanup:
            _cleanup_infra(config)  # type: ignore[arg-type]


def write_local_graph_suite_files(
    *,
    scenario: GraphScenario,
    config: LocalGraphSuiteConfig,
    results: list[RowResult],
    samples_path: Path,
    api_log_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{scenario.name}-graph-api-suite-{config.run_id}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    payload = {
        "scenario": scenario.plan_payload(),
        "suite": {
            "run_id": config.run_id,
            "api_url": config.api_url,
            "workers": config.workers,
            "root_decisions": config.root_decisions,
            "postgres_image": config.postgres_image,
            "redis_image": config.redis_image,
            "postgres_cpus": config.postgres_cpus,
            "postgres_memory": config.postgres_memory,
            "postgres_max_connections": config.postgres_max_connections,
            "postgres_data_dir": str(config.postgres_data_dir) if config.postgres_data_dir else None,
            "redis_cpus": config.redis_cpus,
            "redis_memory": config.redis_memory,
            "db_pool_size": config.db_pool_size,
            "db_max_overflow": config.db_max_overflow,
            "db_pool_timeout_seconds": config.db_pool_timeout_seconds,
            "no_access_log": config.no_access_log,
            "samples_path": str(samples_path),
            "api_log_path": str(api_log_path),
        },
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_local_graph_suite_markdown(
            scenario=scenario,
            config=config,
            results=results,
            samples_path=samples_path,
            api_log_path=api_log_path,
        ),
        encoding="utf-8",
    )
    return json_path, markdown_path


def render_local_graph_suite_markdown(
    *,
    scenario: GraphScenario,
    config: LocalGraphSuiteConfig,
    results: list[RowResult],
    samples_path: Path,
    api_log_path: Path,
) -> str:
    lines = [
        f"# Local Graph Traversal Performance Suite: {scenario.name}",
        "",
        f"Run ID: `{config.run_id}`",
        "",
        "## Environment",
        "",
        "| Component | Value |",
        "| --- | --- |",
        f"| API URL | `{config.api_url}` |",
        f"| API workers | `{config.workers}` |",
        f"| API access log | `{'disabled' if config.no_access_log else 'enabled'}` |",
        f"| Postgres | `{config.postgres_image}` on host port `{config.postgres_port}` |",
        f"| Postgres CPU limit | `{config.postgres_cpus or 'unlimited'}` |",
        f"| Postgres memory limit | `{config.postgres_memory or 'unlimited'}` |",
        f"| Postgres max connections | `{config.postgres_max_connections or 'default'}` |",
        f"| Postgres data dir | `{config.postgres_data_dir or 'docker volume'}` |",
        f"| Redis | `{config.redis_image}` on host port `{config.redis_port}` |",
        f"| Redis CPU limit | `{config.redis_cpus or 'unlimited'}` |",
        f"| Redis memory limit | `{config.redis_memory or 'unlimited'}` |",
        f"| DB pool size | `{config.db_pool_size or 'default'}` |",
        f"| DB max overflow | `{config.db_max_overflow if config.db_max_overflow is not None else 'default'}` |",
        f"| DB pool timeout | `{config.db_pool_timeout_seconds or 'default'}` |",
        f"| Root decision id pool | `{config.root_decisions}` |",
        "",
        "## Results",
        "",
        render_graph_results_markdown(
            _graph_scenario_with_url(scenario, config.api_url), results, layer="graph-api-suite"
        ).strip(),
        "",
        "## Resource Artifacts",
        "",
        f"- Samples CSV: `{samples_path}`",
        f"- API log: `{api_log_path}`",
        "",
        "## Notes",
        "",
        "- Each graph shape truncates and reseeds event/version/decision/link rows before its rows run.",
        "- The suite logs in as a generated admin user and reuses a bearer token for traversal requests.",
        "- Results are local capacity evidence, not a production capacity guarantee.",
        "",
    ]
    return "\n".join(lines)


def parse_graph_api_suite_args(args: Any) -> LocalGraphSuiteConfig:
    return LocalGraphSuiteConfig(
        run_id=str(args.run_id or default_run_id()),
        api_port=int(args.api_port),
        postgres_port=int(args.postgres_port),
        redis_port=int(args.redis_port),
        workers=int(args.workers),
        root_decisions=int(args.root_decisions),
        org_name=str(args.org_name),
        admin_email=str(args.admin_email),
        admin_password=str(args.admin_password),
        postgres_image=str(args.postgres_image),
        redis_image=str(args.redis_image),
        postgres_cpus=args.postgres_cpus,
        postgres_memory=args.postgres_memory,
        postgres_max_connections=args.postgres_max_connections,
        postgres_data_dir=Path(args.postgres_data_dir) if args.postgres_data_dir else None,
        redis_cpus=args.redis_cpus,
        redis_memory=args.redis_memory,
        db_pool_size=args.db_pool_size,
        db_max_overflow=args.db_max_overflow,
        db_pool_timeout_seconds=args.db_pool_timeout_seconds,
        continue_after_breach=bool(args.continue_after_breach),
        no_access_log=not bool(args.access_log),
        cleanup=not bool(args.keep_containers),
        row_filter=args.row_filter,
    )


def main_graph_plan(args: Any, scenario: GraphScenario) -> None:
    json_path, markdown_path = write_graph_plan_files(scenario)
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


def main_graph_run(args: Any, scenario: GraphScenario) -> None:
    bearer_token = os.getenv(str(args.bearer_token_env))
    if not bearer_token:
        raise SystemExit(f"Missing bearer token environment variable: {args.bearer_token_env}")
    raw_ids = os.getenv(str(args.decision_ids_env))
    if not raw_ids:
        raise SystemExit(f"Missing decision ids environment variable: {args.decision_ids_env}")
    decision_ids = [int(value.strip()) for value in raw_ids.split(",") if value.strip()]
    rows = _filtered_graph_rows(scenario, args.row_filter)
    if not rows:
        raise SystemExit("No graph rows matched the requested filter.")
    results = run_graph_scenario(
        scenario=scenario,
        rows=rows,
        bearer_token=bearer_token,
        evaluation_decision_ids=decision_ids,
        continue_after_breach=bool(args.continue_after_breach),
    )
    json_path, markdown_path = write_graph_result_files(scenario, results, layer="graph-api")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


def main_graph_api_suite(args: Any, scenario: GraphScenario) -> None:
    config = parse_graph_api_suite_args(args)
    artifacts = run_local_graph_suite(scenario, config)
    print(f"Wrote {artifacts.json_path}")
    print(f"Wrote {artifacts.markdown_path}")
    print(f"Wrote {artifacts.samples_path}")
    print(f"Wrote {artifacts.api_log_path}")


def _send_graph_requests(
    *,
    scenario: GraphScenario,
    row: GraphTraversalRow,
    bearer_token: str,
    evaluation_decision_ids: list[int],
    request_count: int,
    duration_seconds: int,
) -> list[GraphRequestResult]:
    if request_count == 0:
        return []

    interval = duration_seconds / request_count if request_count > 0 else 0
    start = time.perf_counter()
    futures = []
    httpx = _load_httpx()
    headers = {"Authorization": f"Bearer {bearer_token}"}
    with httpx.Client(timeout=20.0) as client:
        with ThreadPoolExecutor(max_workers=row.step.concurrency) as pool:
            for index in range(request_count):
                scheduled_at = start + (index * interval)
                sleep_for = scheduled_at - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                decision_id = evaluation_decision_ids[index % len(evaluation_decision_ids)]
                futures.append(pool.submit(_send_one_graph, client, scenario.url, headers, row, decision_id))
            return [future.result() for future in as_completed(futures)]


def _send_one_graph(
    client: Any,
    url: str,
    headers: dict[str, str],
    row: GraphTraversalRow,
    evaluation_decision_id: int,
) -> GraphRequestResult:
    start = time.perf_counter()
    try:
        response = client.get(
            f"{url}/api/v2/tested-events/{evaluation_decision_id}/graph",
            params={"max_events": row.max_events, "max_hops": row.max_hops},
            headers=headers,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        if response.status_code != 200:
            return GraphRequestResult(
                ok=False,
                status_code=response.status_code,
                latency_ms=latency_ms,
                evaluation_decision_id=evaluation_decision_id,
                error=response.text[:500],
            )
        payload = response.json()
        return GraphRequestResult(
            ok=True,
            status_code=response.status_code,
            latency_ms=latency_ms,
            evaluation_decision_id=evaluation_decision_id,
            node_count=len(payload.get("nodes", [])),
            edge_count=len(payload.get("edges", [])),
            event_count=int(payload.get("event_count", 0)),
            truncated=bool(payload.get("truncated", False)),
        )
    except Exception as exc:
        return GraphRequestResult(
            ok=False,
            status_code=-1,
            latency_ms=(time.perf_counter() - start) * 1000,
            evaluation_decision_id=evaluation_decision_id,
            error=str(exc),
        )


def _bootstrap_graph_org(config: LocalGraphSuiteConfig) -> None:
    _run(
        [
            "uv",
            "run",
            "ezrules",
            "bootstrap-org",
            "--name",
            config.org_name,
            "--admin-email",
            config.admin_email,
            "--admin-password",
            config.admin_password,
        ],
        env=_suite_env(config, testing=True),  # type: ignore[arg-type]
    )


def _seed_graph_shape(config: LocalGraphSuiteConfig, shape: GraphShape) -> None:
    _truncate_graph_data(config)
    transaction_id_width = _graph_transaction_id_width(shape.event_count)
    _psql(
        config,  # type: ignore[arg-type]
        f"""
with target_org as (
  select o_id from organisation where name = '{_sql_literal(config.org_name)}'
),
inserted_events as (
  insert into event_versions (
    o_id, transaction_id, event_version, effective_at, observed_at, event_data,
    payload_hash, source, terminal_state, ingested_at
  )
  select
    target_org.o_id,
    'GraphPerf-' || lpad(series.event_index::text, {transaction_id_width}, '0'),
    1,
    now() - (({shape.event_count} - series.event_index) || ' seconds')::interval,
    now() - (({shape.event_count} - series.event_index) || ' seconds')::interval,
    jsonb_build_object(
      'transaction_id', 'GraphPerf-' || lpad(series.event_index::text, {transaction_id_width}, '0'),
      'graph_perf', true,
      'amount', 100 + series.event_index,
      'event_index', series.event_index
    ),
    md5('GraphPerf-' || series.event_index::text),
    'performance-graph',
    false,
    now()
  from target_org cross join generate_series(1, {shape.event_count}) as series(event_index)
  returning ev_id, o_id, transaction_id, event_version, effective_at, observed_at
),
inserted_decisions as (
  insert into evaluation_decisions (
    ev_id, o_id, transaction_id, event_version, effective_at, observed_at,
    decision_type, served, is_current, rule_config_label, outcome_counters,
    resolved_outcome, all_rule_results, evaluated_at
  )
  select
    ev_id, o_id, transaction_id, event_version, effective_at, observed_at,
    'served', true, true, 'graph-performance',
    '{{"REVIEW": 1}}'::jsonb, 'REVIEW', '[]'::jsonb, now()
  from inserted_events
  returning ed_id, ev_id, o_id, transaction_id, effective_at, observed_at
)
insert into transaction_current_versions (
  o_id, transaction_id, current_ev_id, current_ed_id, first_effective_at,
  first_observed_at, current_effective_at, current_observed_at, terminal_state, updated_at
)
select
  o_id, transaction_id, ev_id, ed_id, effective_at, observed_at,
  effective_at, observed_at, false, now()
from inserted_decisions;
""",
    )
    value_stride = max(1, math.ceil(shape.shared_entity_count / max(shape.entities_per_event, 1)))
    for slot_index in range(shape.entities_per_event):
        print(f"Seeding graph links slot {slot_index + 1}/{shape.entities_per_event} ...", flush=True)
        field_path = f"graph.entity_{slot_index}"
        entity_type = f"entity_{slot_index % shape.entity_type_count}"
        _psql(
            config,  # type: ignore[arg-type]
            f"""
with selected_events as (
  select
    right(transaction_id, {transaction_id_width})::bigint - 1 as event_offset,
    ev_id,
    o_id,
    transaction_id,
    effective_at
  from event_versions
  where source = 'performance-graph'
    and o_id = (select o_id from organisation where name = '{_sql_literal(config.org_name)}')
)
insert into graph_event_entity_links (
  o_id, ev_id, transaction_id, effective_at, field_path, entity_type,
  entity_value, entity_value_hash, created_at
)
select
  selected_events.o_id,
  selected_events.ev_id,
  selected_events.transaction_id,
  selected_events.effective_at,
  '{_sql_literal(field_path)}',
  '{_sql_literal(entity_type)}',
  'value_' || lpad(
    ((selected_events.event_offset + ({slot_index} * {value_stride})) % {shape.shared_entity_count})::text,
    6,
    '0'
  ),
  md5(
    '{_sql_literal(entity_type)}' || ':value_' ||
    lpad(
      ((selected_events.event_offset + ({slot_index} * {value_stride})) % {shape.shared_entity_count})::text,
      6,
      '0'
    )
  ),
  now()
from selected_events;
""",
        )


def _graph_transaction_id_width(event_count: int) -> int:
    return max(7, len(str(max(event_count, 1))))


def _truncate_graph_data(config: LocalGraphSuiteConfig) -> None:
    _psql(
        config,  # type: ignore[arg-type]
        """
truncate
  graph_event_entity_links,
  evaluation_rule_results,
  rule_deployment_results_log,
  shadow_results_log,
  alert_incidents,
  evaluation_decisions,
  transaction_current_versions,
  event_versions
restart identity cascade;
""",
    )


def _graph_decision_ids(config: LocalGraphSuiteConfig, limit: int) -> list[int]:
    raw = _psql(
        config,  # type: ignore[arg-type]
        f"""
select ed_id
from evaluation_decisions
where o_id = (select o_id from organisation where name = '{_sql_literal(config.org_name)}')
order by ed_id desc
limit {limit};
""",
    )
    return [int(line.strip()) for line in raw.splitlines() if line.strip().isdigit()]


def _login(config: LocalGraphSuiteConfig) -> str:
    httpx = _load_httpx()
    response = httpx.post(
        f"{config.api_url}/api/v2/auth/login",
        data={"username": config.admin_email, "password": config.admin_password},
        timeout=10.0,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _graph_shape_slice(
    scenario: GraphScenario,
    *,
    config: LocalGraphSuiteConfig,
    shape: GraphShape,
) -> GraphScenario:
    return GraphScenario(
        name=f"{scenario.name}-shape-{shape.name}",
        description=scenario.description,
        url=config.api_url,
        graph_shapes=(shape,),
        max_events=scenario.max_events,
        max_hops=scenario.max_hops,
        workload=scenario.workload,
        thresholds=scenario.thresholds,
        output_dir=config.output_dir or scenario.output_dir,
    )


def _graph_scenario_with_url(scenario: GraphScenario, url: str) -> GraphScenario:
    return GraphScenario(
        name=scenario.name,
        description=scenario.description,
        url=url,
        graph_shapes=scenario.graph_shapes,
        max_events=scenario.max_events,
        max_hops=scenario.max_hops,
        workload=scenario.workload,
        thresholds=scenario.thresholds,
        output_dir=scenario.output_dir,
    )


def _filtered_graph_rows(scenario: GraphScenario, row_filter: str | None) -> list[GraphTraversalRow]:
    rows = scenario.rows()
    if row_filter:
        return [row for row in rows if row_filter in row.row_id]
    return rows


def _load_graph_shapes(value: Any) -> list[GraphShape]:
    if not isinstance(value, list) or not value:
        raise ValueError("graph_shapes must be a non-empty list.")
    shapes: list[GraphShape] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each graph shape must be a mapping.")
        shape = GraphShape(
            name=_required_str(item, "name"),
            event_count=_required_positive_int(item, "event_count"),
            entities_per_event=_required_positive_int(item, "entities_per_event"),
            shared_entity_count=_required_positive_int(item, "shared_entity_count"),
            entity_type_count=int(item.get("entity_type_count", 4)),
        )
        if shape.entity_type_count < 1:
            raise ValueError("entity_type_count must be positive.")
        shapes.append(shape)
    return shapes


def _load_workload(value: Any) -> list[WorkloadStep]:
    if not isinstance(value, list):
        raise ValueError("workload must be a list.")
    workload: list[WorkloadStep] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each workload step must be a mapping.")
        workload.append(
            WorkloadStep(
                name=_required_str(item, "name"),
                target_rps=float(item.get("target_rps", 0)),
                duration_seconds=_required_positive_int(item, "duration_seconds"),
                concurrency=_required_positive_int(item, "concurrency"),
                warmup_seconds=int(item.get("warmup_seconds", 0)),
            )
        )
    if any(step.target_rps <= 0 for step in workload):
        raise ValueError("workload target_rps values must be positive.")
    if any(step.warmup_seconds < 0 for step in workload):
        raise ValueError("workload warmup_seconds values cannot be negative.")
    return workload


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing required string: {key}")
    return value


def _required_int_list(raw: dict[str, Any], key: str) -> list[int]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list.")
    parsed = [int(item) for item in value]
    if any(item < 1 for item in parsed):
        raise ValueError(f"{key} values must be positive.")
    return parsed


def _required_positive_int(raw: dict[str, Any], key: str) -> int:
    value = int(raw.get(key, 0))
    if value < 1:
        raise ValueError(f"{key} must be positive.")
    return value


def _load_httpx() -> Any:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Graph performance runs require httpx. Install development dependencies with `uv sync`."
        ) from exc
    return httpx


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


if __name__ == "__main__":
    raise SystemExit("Use `python -m ezrules.performance.runner graph-api-suite <scenario>`.")


def _with_graph_threshold_breaches(result: RowResult, scenario: GraphScenario) -> RowResult:
    breaches: list[str] = []
    if result.failure_rate > scenario.thresholds.max_failure_rate:
        breaches.append("failure_rate")
    if result.latency_p95_ms is None or result.latency_p95_ms > scenario.thresholds.max_p95_ms:
        breaches.append("p95_latency")
    if result.latency_p99_ms is None or result.latency_p99_ms > scenario.thresholds.max_p99_ms:
        breaches.append("p99_latency")
    return RowResult(
        layer=result.layer,
        row_id=result.row_id,
        started_at=result.started_at,
        completed_at=result.completed_at,
        planned_requests=result.planned_requests,
        ok=result.ok,
        failed=result.failed,
        failure_rate=result.failure_rate,
        achieved_rps=result.achieved_rps,
        latency_min_ms=result.latency_min_ms,
        latency_p50_ms=result.latency_p50_ms,
        latency_p95_ms=result.latency_p95_ms,
        latency_p99_ms=result.latency_p99_ms,
        latency_max_ms=result.latency_max_ms,
        status_counts=result.status_counts,
        first_error=result.first_error,
        breached_thresholds=breaches,
    )
