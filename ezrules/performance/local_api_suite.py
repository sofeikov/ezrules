from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ezrules.performance.matrix import MatrixRow, OrganisationTarget, Scenario
from ezrules.performance.runner import RowResult, render_results_markdown, run_scenario


@dataclass(frozen=True, slots=True)
class LocalApiSuiteConfig:
    """Runtime settings for a disposable local API performance suite."""

    run_id: str
    api_port: int
    postgres_port: int
    redis_port: int
    workers: int
    seed_events: int
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
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", self.run_id).strip("_").lower()
        return normalized or "run"

    @property
    def docker_resource_id(self) -> str:
        return self.resource_id.replace("_", "-").lower()

    @property
    def db_name(self) -> str:
        return f"ezrules_perf_suite_{self.resource_id}"

    @property
    def postgres_container(self) -> str:
        return f"ezrules-perf-postgres-{self.docker_resource_id}"

    @property
    def redis_container(self) -> str:
        return f"ezrules-perf-redis-{self.docker_resource_id}"

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
class LocalApiSuiteArtifacts:
    """Paths produced by a local API performance suite run."""

    json_path: Path
    markdown_path: Path
    samples_path: Path
    api_log_path: Path


class CommandError(RuntimeError):
    """Raised when an orchestration command fails."""


def default_run_id() -> str:
    """Return a compact timestamped run id for local Docker resources and artifacts."""
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def run_local_api_suite(scenario: Scenario, config: LocalApiSuiteConfig) -> LocalApiSuiteArtifacts:
    """Run a reproducible local API suite using disposable Docker Postgres/Redis."""

    output_dir = config.output_dir or scenario.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    api_log_path = output_dir / f"{scenario.name}-api-suite-{config.run_id}-api.log"
    samples_path = output_dir / f"{scenario.name}-api-suite-{config.run_id}-samples.csv"

    results: list[RowResult] = []
    api_process: subprocess.Popen | None = None
    sampler: ResourceSampler | None = None

    try:
        _start_infra(config)
        _initialize_database(config)
        org_keys = _seed_targets(scenario, config)
        sampler = ResourceSampler(
            samples_path=samples_path,
            config=config,
        )
        sampler.start()

        for rule_count in scenario.rule_counts:
            for rule_complexity in scenario.rule_complexities:
                _seed_rule_count(scenario, config, rule_count, rule_complexity)
                for execution_mode in scenario.execution_modes:
                    _set_execution_mode(scenario.organisations, config, execution_mode)
                    _reset_pg_stat_statements(config)

                    _stop_process(api_process)
                    api_process = _start_api(config, api_log_path)
                    _wait_for_api(config.api_url)

                    suite_scenario = _scenario_slice(
                        scenario,
                        config=config,
                        rule_count=rule_count,
                        rule_complexity=rule_complexity,
                        execution_mode=execution_mode,
                    )
                    suite_rows = _filtered_rows(suite_scenario, config.row_filter)
                    if not suite_rows:
                        continue

                    original_env = _install_api_key_env(org_keys)
                    try:
                        results.extend(
                            run_scenario(
                                scenario=suite_scenario,
                                rows=suite_rows,
                                continue_after_breach=config.continue_after_breach,
                            )
                        )
                    finally:
                        _restore_env(original_env, org_keys)

        json_path, markdown_path = write_api_suite_files(
            scenario=scenario,
            config=config,
            results=results,
            samples_path=samples_path,
            api_log_path=api_log_path,
            output_dir=output_dir,
        )
        return LocalApiSuiteArtifacts(
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
            _cleanup_infra(config)


def write_api_suite_files(
    *,
    scenario: Scenario,
    config: LocalApiSuiteConfig,
    results: list[RowResult],
    samples_path: Path,
    api_log_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{scenario.name}-api-suite-{config.run_id}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    payload = {
        "scenario": scenario.plan_payload(),
        "suite": {
            "run_id": config.run_id,
            "api_url": config.api_url,
            "workers": config.workers,
            "seed_events": config.seed_events,
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
        render_api_suite_markdown(
            scenario=scenario,
            config=config,
            results=results,
            samples_path=samples_path,
            api_log_path=api_log_path,
        ),
        encoding="utf-8",
    )
    return json_path, markdown_path


def render_api_suite_markdown(
    *,
    scenario: Scenario,
    config: LocalApiSuiteConfig,
    results: list[RowResult],
    samples_path: Path,
    api_log_path: Path,
) -> str:
    lines = [
        f"# Local API Performance Suite: {scenario.name}",
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
        f"| Seed events per org/rule-count/complexity block | `{config.seed_events}` |",
        "",
        "## Results",
        "",
        render_results_markdown(scenario, results, layer="api-suite").strip(),
        "",
        "## Resource Artifacts",
        "",
        f"- Samples CSV: `{samples_path}`",
        f"- API log: `{api_log_path}`",
        "",
        "## Notes",
        "",
        "- The suite recreates the database once, then reseeds each configured rule-count/complexity block before running its mode slices.",
        "- API keys are generated in memory for the run and are not written to result artifacts.",
        "- Results are local capacity evidence, not a production capacity guarantee.",
        "",
    ]
    return "\n".join(lines)


def _scenario_slice(
    scenario: Scenario,
    *,
    config: LocalApiSuiteConfig,
    rule_count: int,
    rule_complexity: str,
    execution_mode: str,
) -> Scenario:
    return Scenario(
        name=f"{scenario.name}-rules-{rule_count}-{execution_mode}",
        description=scenario.description,
        url=config.api_url,
        organisations=scenario.organisations,
        rule_counts=(rule_count,),
        execution_modes=(execution_mode,),
        match_profiles=scenario.match_profiles,
        rule_complexities=(rule_complexity,),
        workload=scenario.workload,
        thresholds=scenario.thresholds,
        output_dir=config.output_dir or scenario.output_dir,
    )


def _filtered_rows(scenario: Scenario, row_filter: str | None) -> list[MatrixRow]:
    rows = scenario.rows()
    if row_filter:
        return [row for row in rows if row_filter in row.row_id]
    return rows


def _start_infra(config: LocalApiSuiteConfig) -> None:
    _cleanup_infra(config)
    postgres_args = [
        "-c",
        "shared_preload_libraries=pg_stat_statements",
        "-c",
        "track_io_timing=on",
    ]
    if config.postgres_max_connections is not None:
        postgres_args.extend(["-c", f"max_connections={config.postgres_max_connections}"])
    volume_args: list[str] = []
    if config.postgres_data_dir is not None:
        config.postgres_data_dir.mkdir(parents=True, exist_ok=True)
        volume_args = ["-v", f"{config.postgres_data_dir.resolve()}:/var/lib/postgresql/data"]
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            config.postgres_container,
            "-e",
            "POSTGRES_PASSWORD=root",
            *volume_args,
            "-p",
            f"{config.postgres_port}:5432",
            *_docker_resource_args(config.postgres_cpus, config.postgres_memory),
            config.postgres_image,
            *postgres_args,
        ]
    )
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            config.redis_container,
            "-p",
            f"{config.redis_port}:6379",
            *_docker_resource_args(config.redis_cpus, config.redis_memory),
            config.redis_image,
        ]
    )
    time.sleep(2)


def _cleanup_infra(config: LocalApiSuiteConfig) -> None:
    _run(["docker", "rm", "-f", config.postgres_container, config.redis_container], check=False)


def _initialize_database(config: LocalApiSuiteConfig) -> None:
    env = _suite_env(config, testing=True)
    _run(["uv", "run", "ezrules", "init-db", "--auto-delete"], env=env)
    _psql(config, "create extension if not exists pg_stat_statements;")


def _seed_targets(scenario: Scenario, config: LocalApiSuiteConfig) -> dict[str, str]:
    org_keys: dict[str, str] = {}
    for index, org in enumerate(scenario.organisations, start=1):
        admin_email = f"perf-{config.run_id}-{index}@example.com"
        _run(
            [
                "uv",
                "run",
                "ezrules",
                "bootstrap-org",
                "--name",
                org.name,
                "--admin-email",
                admin_email,
                "--admin-password",
                "admin",
            ],
            env=_suite_env(config, testing=True),
        )
        org_keys[org.api_key_env] = _create_api_key(config, org.name, index)
    return org_keys


def _seed_rule_count(scenario: Scenario, config: LocalApiSuiteConfig, rule_count: int, rule_complexity: str) -> None:
    _truncate_seeded_data(config)
    for org in scenario.organisations:
        _run(
            [
                "uv",
                "run",
                "ezrules",
                "generate-random-data",
                "--n-rules",
                str(rule_count),
                "--n-events",
                str(config.seed_events),
                "--label-ratio",
                "0",
                "--rule-complexity",
                rule_complexity,
                "--org-name",
                org.name,
            ],
            env=_suite_env(config, testing=True),
        )


def _truncate_seeded_data(config: LocalApiSuiteConfig) -> None:
    _psql(
        config,
        """
truncate
  evaluation_rule_results,
  rule_deployment_results_log,
  shadow_results_log,
  alert_incidents,
  evaluation_decisions,
  transaction_current_versions,
  event_versions,
  field_observation,
  rules,
  rule_engine_config,
  rule_engine_config_history
restart identity cascade;
""",
    )


def _create_api_key(config: LocalApiSuiteConfig, org_name: str, index: int) -> str:
    raw_key = "ezrk_perf_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    gid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ezrules-performance:{config.run_id}:{org_name}:{index}"))
    _psql(
        config,
        f"""
insert into api_keys (gid, key_hash, label, created_at, o_id)
select '{gid}', '{key_hash}', 'performance-suite', now(), o_id
from organisation
where name = '{_sql_literal(org_name)}';
""",
    )
    return raw_key


def _set_execution_mode(organisations: tuple[OrganisationTarget, ...], config: LocalApiSuiteConfig, mode: str) -> None:
    org_names = ", ".join(f"'{_sql_literal(org.name)}'" for org in organisations)
    _psql(
        config,
        f"""
insert into runtime_settings (key, o_id, value_type, value, created_at, updated_at)
select 'main_rule_execution_mode', o_id, 'string', '{_sql_literal(mode)}', now(), now()
from organisation
where name in ({org_names})
on conflict (key, o_id) do update
set value = excluded.value,
    value_type = excluded.value_type,
    updated_at = now();
""",
    )


def _reset_pg_stat_statements(config: LocalApiSuiteConfig) -> None:
    _psql(config, "select pg_stat_statements_reset();")


def _start_api(config: LocalApiSuiteConfig, api_log_path: Path) -> subprocess.Popen:
    env = _suite_env(config, testing=False)
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "uvicorn",
        "ezrules.backend.api_v2.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(config.api_port),
        "--workers",
        str(config.workers),
    ]
    if config.no_access_log:
        command.append("--no-access-log")
    api_log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = api_log_path.open("a", encoding="utf-8")
    try:
        return subprocess.Popen(command, env=env, stdout=log_file, stderr=subprocess.STDOUT, text=True)
    finally:
        log_file.close()


def _wait_for_api(api_url: str, timeout_seconds: int = 30) -> None:
    httpx = _load_httpx()
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{api_url}/ping", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(f"API at {api_url} did not become healthy: {last_error}")


def _load_httpx() -> Any:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Local API performance suites require httpx. Install development dependencies with `uv sync`."
        ) from exc
    return httpx


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    with suppress(ProcessLookupError):
        process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def _suite_env(config: LocalApiSuiteConfig, *, testing: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "EZRULES_DB_ENDPOINT": config.db_endpoint,
            "EZRULES_APP_SECRET": "performance-suite-secret",
            "EZRULES_TESTING": "true" if testing else "false",
            "EZRULES_CELERY_BROKER_URL": config.redis_url,
            "EZRULES_OBSERVATION_QUEUE_REDIS_URL": config.redis_url,
            "EZRULES_SHADOW_EVALUATION_QUEUE_REDIS_URL": config.redis_url,
        }
    )
    if config.db_pool_size is not None:
        env["EZRULES_DB_POOL_SIZE"] = str(config.db_pool_size)
    if config.db_max_overflow is not None:
        env["EZRULES_DB_MAX_OVERFLOW"] = str(config.db_max_overflow)
    if config.db_pool_timeout_seconds is not None:
        env["EZRULES_DB_POOL_TIMEOUT_SECONDS"] = str(config.db_pool_timeout_seconds)
    return env


def _install_api_key_env(org_keys: dict[str, str]) -> dict[str, str | None]:
    original = {name: os.environ.get(name) for name in org_keys}
    os.environ.update(org_keys)
    return original


def _restore_env(original: dict[str, str | None], org_keys: dict[str, str]) -> None:
    for name in org_keys:
        old_value = original.get(name)
        if old_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old_value


def _psql(config: LocalApiSuiteConfig, sql: str) -> str:
    return _run(
        [
            "docker",
            "exec",
            "-i",
            config.postgres_container,
            "psql",
            "-U",
            "postgres",
            "-d",
            config.db_name,
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
        ],
        input_text=sql,
    ).stdout


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=Path.cwd(),
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CommandError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
    return result


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


class ResourceSampler:
    """Sample API process, Docker, and Postgres wait-state metrics once per second."""

    header = (
        "timestamp,api_processes,api_cpu_percent_sum,api_rss_kb_sum,postgres_cpu_percent,postgres_mem_usage,"
        "redis_cpu_percent,redis_mem_usage,total_connections,active_connections,idle_in_transaction,"
        "waiting_connections,lock_waiting,io_waiting,client_waiting,max_query_age_seconds,blocked_locks\n"
    )

    def __init__(self, *, samples_path: Path, config: LocalApiSuiteConfig) -> None:
        self.samples_path = samples_path
        self.config = config
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.samples_path.parent.mkdir(parents=True, exist_ok=True)
        self.samples_path.write_text(self.header, encoding="utf-8")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            with suppress(Exception):
                self._sample_once()
            self._stop.wait(1)

    def _sample_once(self) -> None:
        api_processes, api_cpu, api_rss = self._api_stats()
        postgres_cpu, postgres_mem = self._docker_stats(self.config.postgres_container)
        redis_cpu, redis_mem = self._docker_stats(self.config.redis_container)
        db_values = self._db_values()
        line = (
            f"{datetime.now(UTC).isoformat()},"
            f"{api_processes},{api_cpu:.2f},{api_rss},"
            f'{postgres_cpu:.2f},"{postgres_mem}",'
            f'{redis_cpu:.2f},"{redis_mem}",'
            f"{db_values}\n"
        )
        with self.samples_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _api_stats(self) -> tuple[int, float, int]:
        roots = _run(
            ["pgrep", "-f", f"uvicorn ezrules.backend.api_v2.main:app.*--port {self.config.api_port}"],
            check=False,
        ).stdout.split()
        pids = _collect_process_tree(roots)
        if not pids:
            return 0, 0.0, 0
        result = _run(["ps", "-p", ",".join(pids), "-o", "pcpu=,rss="], check=False)
        cpu = 0.0
        rss = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                cpu += float(parts[0])
                rss += int(parts[1])
        return len(pids), cpu, rss

    def _docker_stats(self, container_name: str) -> tuple[float, str]:
        result = _run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}},{{.MemUsage}}", container_name],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0.0, ""
        cpu_raw, _, mem_raw = result.stdout.strip().partition(",")
        return float(cpu_raw.strip().removesuffix("%") or 0), mem_raw.strip()

    def _db_values(self) -> str:
        sql = """
with activity as (
  select
    count(*) as total_connections,
    count(*) filter (where state = 'active') as active_connections,
    count(*) filter (where state = 'idle in transaction') as idle_in_transaction,
    count(*) filter (where wait_event_type is not null) as waiting_connections,
    count(*) filter (where wait_event_type = 'Lock') as lock_waiting,
    count(*) filter (where wait_event_type = 'IO') as io_waiting,
    count(*) filter (where wait_event_type = 'Client') as client_waiting,
    coalesce(max(extract(epoch from now() - query_start)) filter (where state = 'active'), 0) as max_query_age_seconds
  from pg_stat_activity
  where datname = current_database()
),
blocked as (
  select count(*) as blocked_locks
  from pg_locks
  where database = (select oid from pg_database where datname = current_database())
    and not granted
)
select
  activity.total_connections,
  activity.active_connections,
  activity.idle_in_transaction,
  activity.waiting_connections,
  activity.lock_waiting,
  activity.io_waiting,
  activity.client_waiting,
  round(activity.max_query_age_seconds::numeric, 3),
  blocked.blocked_locks
from activity cross join blocked;
"""
        result = _run(
            [
                "docker",
                "exec",
                self.config.postgres_container,
                "psql",
                "-U",
                "postgres",
                "-d",
                self.config.db_name,
                "-At",
                "-F,",
                "-c",
                sql,
            ],
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "0,0,0,0,0,0,0,0,0"


def _collect_process_tree(roots: list[str]) -> list[str]:
    seen: set[str] = set()
    frontier = [pid for pid in roots if pid.isdigit()]
    while frontier:
        pid = frontier.pop()
        if pid in seen:
            continue
        seen.add(pid)
        children = _run(["pgrep", "-P", pid], check=False).stdout.split()
        frontier.extend(child for child in children if child.isdigit() and child not in seen)
    return sorted(seen, key=int)


def parse_api_suite_args(args: Any) -> LocalApiSuiteConfig:
    run_id = args.run_id or default_run_id()
    return LocalApiSuiteConfig(
        run_id=str(run_id),
        api_port=int(args.api_port),
        postgres_port=int(args.postgres_port),
        redis_port=int(args.redis_port),
        workers=int(args.workers),
        seed_events=int(args.seed_events),
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


def main_from_args(args: Any, scenario: Scenario) -> None:
    config = parse_api_suite_args(args)
    artifacts = run_local_api_suite(scenario, config)
    print(f"Wrote {artifacts.json_path}")
    print(f"Wrote {artifacts.markdown_path}")
    print(f"Wrote {artifacts.samples_path}")
    print(f"Wrote {artifacts.api_log_path}")


if __name__ == "__main__":
    raise SystemExit("Use `python -m ezrules.performance.runner api-suite <scenario>`.")


def _docker_resource_args(cpus: str | None, memory: str | None) -> list[str]:
    args: list[str] = []
    if cpus:
        args.extend(["--cpus", str(cpus)])
    if memory:
        args.extend(["--memory", str(memory)])
    return args
