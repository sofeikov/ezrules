from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ezrules.performance.engine import time_rule_engine
from ezrules.performance.events import build_evaluate_payload
from ezrules.performance.matrix import MatrixRow, OrganisationTarget, Scenario, load_scenario, write_plan_files


@dataclass(frozen=True, slots=True)
class ResolvedOrganisation:
    name: str
    api_key_env: str
    api_key: str
    weight: int


@dataclass(frozen=True, slots=True)
class RequestResult:
    ok: bool
    status_code: int
    latency_ms: float
    organisation: str
    transaction_id: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RowResult:
    layer: str
    row_id: str
    started_at: str
    completed_at: str
    planned_requests: int
    ok: int
    failed: int
    failure_rate: float
    achieved_rps: float
    latency_min_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    latency_max_ms: float | None
    status_counts: dict[str, int]
    first_error: str | None
    breached_thresholds: list[str]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible ezrules performance matrices.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Write JSON and Markdown plan artifacts without sending traffic.")
    plan_parser.add_argument("scenario", help="Path to a performance scenario YAML file.")

    run_parser = subparsers.add_parser("run", help="Run a scenario against a live API target.")
    run_parser.add_argument("scenario", help="Path to a performance scenario YAML file.")
    run_parser.add_argument("--row-filter", help="Only run rows whose row_id contains this string.")
    run_parser.add_argument(
        "--continue-after-breach",
        action="store_true",
        help="Keep running later rows after a row breaches the configured thresholds.",
    )

    engine_parser = subparsers.add_parser(
        "engine",
        help="Run the same matrix in pure Python without HTTP, auth, or database writes.",
    )
    engine_parser.add_argument("scenario", help="Path to a performance scenario YAML file.")
    engine_parser.add_argument("--row-filter", help="Only run rows whose row_id contains this string.")
    engine_parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Rule-engine evaluations per row (default 1000).",
    )

    api_suite_parser = subparsers.add_parser(
        "api-suite",
        help="Run a reproducible local API suite with disposable Docker Postgres/Redis.",
    )
    api_suite_parser.add_argument("scenario", help="Path to a performance scenario YAML file.")
    api_suite_parser.add_argument("--row-filter", help="Only run rows whose row_id contains this string.")
    api_suite_parser.add_argument("--run-id", help="Stable id for containers and artifacts. Defaults to UTC timestamp.")
    api_suite_parser.add_argument("--api-port", type=int, default=18888)
    api_suite_parser.add_argument("--postgres-port", type=int, default=55432)
    api_suite_parser.add_argument("--redis-port", type=int, default=56379)
    api_suite_parser.add_argument("--workers", type=int, default=4)
    api_suite_parser.add_argument("--seed-events", type=int, default=100)
    api_suite_parser.add_argument("--postgres-image", default="postgres:16.0-alpine3.18")
    api_suite_parser.add_argument("--redis-image", default="redis:7-alpine")
    api_suite_parser.add_argument(
        "--continue-after-breach",
        action="store_true",
        help="Keep running later rows after a row breaches the configured thresholds.",
    )
    api_suite_parser.add_argument(
        "--access-log",
        action="store_true",
        help="Keep Uvicorn access logging enabled. Disabled by default because it distorts high-RPS runs.",
    )
    api_suite_parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Leave local Docker containers running after the suite exits.",
    )

    args = parser.parse_args()
    scenario = load_scenario(args.scenario)

    if args.command == "plan":
        json_path, markdown_path = write_plan_files(scenario)
        print(f"Wrote {json_path}")
        print(f"Wrote {markdown_path}")
        return

    if args.command == "api-suite":
        from ezrules.performance.local_api_suite import main_from_args

        main_from_args(args, scenario)
        return

    rows = scenario.rows()
    if args.row_filter:
        rows = [row for row in rows if args.row_filter in row.row_id]
    if not rows:
        raise SystemExit("No matrix rows matched the requested filter.")

    if args.command == "engine":
        if args.iterations < 1:
            raise SystemExit("--iterations must be at least 1.")
        results = run_engine_scenario(scenario=scenario, rows=rows, iterations=int(args.iterations))
        json_path, markdown_path = write_result_files(scenario, results, layer="rule-engine")
        print(f"Wrote {json_path}")
        print(f"Wrote {markdown_path}")
        return

    results = run_scenario(
        scenario=scenario,
        rows=rows,
        continue_after_breach=bool(args.continue_after_breach),
    )
    json_path, markdown_path = write_result_files(scenario, results, layer="api-ingestion")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


def run_engine_scenario(*, scenario: Scenario, rows: list[MatrixRow], iterations: int) -> list[RowResult]:
    results: list[RowResult] = []
    for row in rows:
        print(f"Timing rule engine {row.row_id} ...", flush=True)
        started = datetime.now(UTC)
        timing = time_rule_engine(
            rule_count=row.rule_count,
            execution_mode=row.execution_mode,
            match_profile=row.match_profile,
            iterations=iterations,
        )
        completed = datetime.now(UTC)
        result = RowResult(
            layer="rule-engine",
            row_id=row.row_id,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            planned_requests=timing.iterations,
            ok=timing.iterations,
            failed=0,
            failure_rate=0.0,
            achieved_rps=timing.evaluations_per_second,
            latency_min_ms=timing.latency_min_ms,
            latency_p50_ms=timing.latency_p50_ms,
            latency_p95_ms=timing.latency_p95_ms,
            latency_p99_ms=timing.latency_p99_ms,
            latency_max_ms=timing.latency_max_ms,
            status_counts={"engine": timing.iterations},
            first_error=None,
            breached_thresholds=[],
        )
        result = _with_threshold_breaches(result, scenario)
        results.append(result)
        print(
            f"  eval/s={result.achieved_rps:.1f} p95={_format_latency(result.latency_p95_ms)} "
            f"p99={_format_latency(result.latency_p99_ms)} breaches={','.join(result.breached_thresholds) or 'none'}",
            flush=True,
        )
    return results


def run_scenario(
    *,
    scenario: Scenario,
    rows: list[MatrixRow],
    continue_after_breach: bool = False,
) -> list[RowResult]:
    organisations = resolve_organisations(scenario.organisations)
    results: list[RowResult] = []
    for row in rows:
        print(f"Running {row.row_id} ...", flush=True)
        result = run_row(scenario=scenario, row=row, organisations=organisations)
        results.append(result)
        print(
            f"  ok={result.ok} failed={result.failed} "
            f"rps={result.achieved_rps:.1f} p95={_format_latency(result.latency_p95_ms)} "
            f"breaches={','.join(result.breached_thresholds) or 'none'}",
            flush=True,
        )
        if result.breached_thresholds and not continue_after_breach:
            print("Stopping after first threshold breach. Use --continue-after-breach to run remaining rows.")
            break
    return results


def run_row(
    *,
    scenario: Scenario,
    row: MatrixRow,
    organisations: list[ResolvedOrganisation],
) -> RowResult:
    started = datetime.now(UTC)
    warmup_requests = _request_count(row.step.target_rps, row.step.warmup_seconds)
    measured_requests = _request_count(row.step.target_rps, row.step.duration_seconds)
    if warmup_requests:
        _send_requests(
            scenario=scenario,
            row=row,
            organisations=organisations,
            request_count=warmup_requests,
            duration_seconds=row.step.warmup_seconds,
            transaction_prefix=f"warmup-{started.strftime('%Y%m%d%H%M%S')}",
        )

    measure_start = time.perf_counter()
    request_results = _send_requests(
        scenario=scenario,
        row=row,
        organisations=organisations,
        request_count=measured_requests,
        duration_seconds=row.step.duration_seconds,
        transaction_prefix=f"perf-{started.strftime('%Y%m%d%H%M%S')}",
    )
    elapsed = time.perf_counter() - measure_start
    completed = datetime.now(UTC)

    ok_results = [result for result in request_results if result.ok]
    latencies = sorted(result.latency_ms for result in ok_results)
    failed = len(request_results) - len(ok_results)
    failure_rate = failed / len(request_results) if request_results else 0.0
    status_counts: dict[str, int] = {}
    for result in request_results:
        key = str(result.status_code)
        status_counts[key] = status_counts.get(key, 0) + 1

    row_result = RowResult(
        layer="api-ingestion",
        row_id=row.row_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        planned_requests=measured_requests,
        ok=len(ok_results),
        failed=failed,
        failure_rate=failure_rate,
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
    return _with_threshold_breaches(row_result, scenario)


def resolve_organisations(organisations: tuple[OrganisationTarget, ...]) -> list[ResolvedOrganisation]:
    resolved: list[ResolvedOrganisation] = []
    for org in organisations:
        resolved.append(
            ResolvedOrganisation(
                name=org.name,
                api_key_env=org.api_key_env,
                api_key=org.resolve_api_key(),
                weight=org.weight,
            )
        )
    return resolved


def write_result_files(scenario: Scenario, results: list[RowResult], *, layer: str) -> tuple[Path, Path]:
    scenario.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{scenario.name}-{layer}-{timestamp}"
    payload = {
        "scenario": scenario.plan_payload(),
        "results": [asdict(result) for result in results],
    }
    json_path = scenario.output_dir / f"{stem}.json"
    markdown_path = scenario.output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_results_markdown(scenario, results, layer=layer), encoding="utf-8")
    return json_path, markdown_path


def render_results_markdown(scenario: Scenario, results: list[RowResult], *, layer: str) -> str:
    lines = [
        f"# Performance Results: {scenario.name}",
        "",
        f"Layer: `{layer}`",
        f"Target: `{scenario.url}`",
        "",
        "| Row | OK | Failed | Failure Rate | RPS | p50 | p95 | p99 | Breaches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(
            "| "
            f"`{result.row_id}` | {result.ok} | {result.failed} | {result.failure_rate:.4f} | "
            f"{result.achieved_rps:.1f} | {_format_latency(result.latency_p50_ms)} | "
            f"{_format_latency(result.latency_p95_ms)} | {_format_latency(result.latency_p99_ms)} | "
            f"{', '.join(result.breached_thresholds) or 'none'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _send_requests(
    *,
    scenario: Scenario,
    row: MatrixRow,
    organisations: list[ResolvedOrganisation],
    request_count: int,
    duration_seconds: int,
    transaction_prefix: str,
) -> list[RequestResult]:
    if request_count == 0:
        return []

    weighted_orgs = [org for org in organisations for _ in range(org.weight)]
    interval = duration_seconds / request_count if request_count > 0 else 0
    start = time.perf_counter()
    futures = []
    with httpx.Client(timeout=10.0) as client:
        with ThreadPoolExecutor(max_workers=row.step.concurrency) as pool:
            for index in range(request_count):
                scheduled_at = start + (index * interval)
                sleep_for = scheduled_at - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                org = weighted_orgs[index % len(weighted_orgs)]
                futures.append(
                    pool.submit(
                        _send_one,
                        client,
                        scenario.url,
                        org,
                        row,
                        f"{transaction_prefix}-{row.row_id}-{org.name}-{index:08d}",
                        index,
                    )
                )
            return [future.result() for future in as_completed(futures)]


def _send_one(
    client: httpx.Client,
    url: str,
    org: ResolvedOrganisation,
    row: MatrixRow,
    transaction_id: str,
    seed: int,
) -> RequestResult:
    payload = build_evaluate_payload(
        transaction_id=transaction_id,
        match_profile=row.match_profile,
        seed=seed,
    )
    headers = {"X-API-Key": org.api_key}
    start = time.perf_counter()
    try:
        response = client.post(f"{url}/api/v2/evaluate", json=payload, headers=headers)
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            ok=response.status_code == 200,
            status_code=response.status_code,
            latency_ms=latency_ms,
            organisation=org.name,
            transaction_id=transaction_id,
            error=None if response.status_code == 200 else response.text[:500],
        )
    except Exception as exc:
        return RequestResult(
            ok=False,
            status_code=-1,
            latency_ms=(time.perf_counter() - start) * 1000,
            organisation=org.name,
            transaction_id=transaction_id,
            error=str(exc),
        )


def _request_count(target_rps: float, duration_seconds: int) -> int:
    return int(math.ceil(target_rps * duration_seconds))


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    if percentile == 50:
        return statistics.median(values)
    index = math.ceil((percentile / 100) * len(values)) - 1
    return values[min(max(index, 0), len(values) - 1)]


def _with_threshold_breaches(result: RowResult, scenario: Scenario) -> RowResult:
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


def _format_latency(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0f}ms"


if __name__ == "__main__":
    main()
