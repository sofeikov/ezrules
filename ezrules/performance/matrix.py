from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_FAILURE_RATE_THRESHOLD = 0.001
DEFAULT_P95_MS_THRESHOLD = 500.0
DEFAULT_P99_MS_THRESHOLD = 1000.0


@dataclass(frozen=True, slots=True)
class OrganisationTarget:
    """One evaluator credential target, normally representing one customer organisation."""

    name: str
    api_key_env: str
    weight: int = 1

    def resolve_api_key(self) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {self.api_key_env}")
        return api_key


@dataclass(frozen=True, slots=True)
class WorkloadStep:
    """One load level in a fixed or ramped benchmark run."""

    name: str
    target_rps: float
    duration_seconds: int
    concurrency: int
    warmup_seconds: int = 0


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Failure thresholds used to decide where a target starts breaking down."""

    max_failure_rate: float = DEFAULT_FAILURE_RATE_THRESHOLD
    max_p95_ms: float = DEFAULT_P95_MS_THRESHOLD
    max_p99_ms: float = DEFAULT_P99_MS_THRESHOLD


@dataclass(frozen=True, slots=True)
class MatrixRow:
    """A single labelled performance run."""

    row_id: str
    rule_count: int
    execution_mode: str
    match_profile: str
    rule_complexity: str
    step: WorkloadStep


@dataclass(frozen=True, slots=True)
class Scenario:
    """Loaded benchmark matrix configuration."""

    name: str
    description: str
    url: str
    organisations: tuple[OrganisationTarget, ...]
    rule_counts: tuple[int, ...]
    execution_modes: tuple[str, ...]
    match_profiles: tuple[str, ...]
    rule_complexities: tuple[str, ...]
    workload: tuple[WorkloadStep, ...]
    thresholds: Thresholds
    output_dir: Path

    def rows(self) -> list[MatrixRow]:
        rows: list[MatrixRow] = []
        for rule_count in self.rule_counts:
            for execution_mode in self.execution_modes:
                for match_profile in self.match_profiles:
                    for rule_complexity in self.rule_complexities:
                        for step in self.workload:
                            row_id = (
                                f"rules-{rule_count}__mode-{execution_mode}__profile-{match_profile}__"
                                f"complexity-{rule_complexity}__load-{step.name}"
                            )
                            rows.append(
                                MatrixRow(
                                    row_id=row_id,
                                    rule_count=rule_count,
                                    execution_mode=execution_mode,
                                    match_profile=match_profile,
                                    rule_complexity=rule_complexity,
                                    step=step,
                                )
                            )
        return rows

    def plan_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "organisations": [
                {"name": org.name, "api_key_env": org.api_key_env, "weight": org.weight} for org in self.organisations
            ],
            "thresholds": {
                "max_failure_rate": self.thresholds.max_failure_rate,
                "max_p95_ms": self.thresholds.max_p95_ms,
                "max_p99_ms": self.thresholds.max_p99_ms,
            },
            "rows": [
                {
                    "row_id": row.row_id,
                    "rule_count": row.rule_count,
                    "execution_mode": row.execution_mode,
                    "match_profile": row.match_profile,
                    "rule_complexity": row.rule_complexity,
                    "target_rps": row.step.target_rps,
                    "duration_seconds": row.step.duration_seconds,
                    "warmup_seconds": row.step.warmup_seconds,
                    "concurrency": row.step.concurrency,
                }
                for row in self.rows()
            ],
        }


def load_scenario(path: str | Path) -> Scenario:
    """Load a performance matrix scenario from YAML."""

    scenario_path = Path(path)
    raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Scenario file must contain a YAML mapping.")

    name = _required_str(raw, "name")
    description = str(raw.get("description", "")).strip()
    url = str(raw.get("url", "http://localhost:8888")).rstrip("/")
    output_dir = Path(str(raw.get("output_dir", "artifacts/performance")))

    organisations = tuple(_load_organisations(raw.get("organisations")))
    if not organisations:
        raise ValueError("Scenario must define at least one organisation target.")

    rule_counts = tuple(_required_int_list(raw, "rule_counts"))
    execution_modes = tuple(_required_str_list(raw, "execution_modes"))
    match_profiles = tuple(_required_str_list(raw, "match_profiles"))
    rule_complexities = tuple(_required_str_list(raw, "rule_complexities"))
    workload = tuple(_load_workload(raw.get("workload")))
    if not workload:
        raise ValueError("Scenario must define at least one workload step.")

    thresholds_raw = raw.get("thresholds") or {}
    if not isinstance(thresholds_raw, dict):
        raise ValueError("thresholds must be a mapping when provided.")
    thresholds = Thresholds(
        max_failure_rate=float(thresholds_raw.get("max_failure_rate", DEFAULT_FAILURE_RATE_THRESHOLD)),
        max_p95_ms=float(thresholds_raw.get("max_p95_ms", DEFAULT_P95_MS_THRESHOLD)),
        max_p99_ms=float(thresholds_raw.get("max_p99_ms", DEFAULT_P99_MS_THRESHOLD)),
    )

    return Scenario(
        name=name,
        description=description,
        url=url,
        organisations=organisations,
        rule_counts=rule_counts,
        execution_modes=execution_modes,
        match_profiles=match_profiles,
        rule_complexities=rule_complexities,
        workload=workload,
        thresholds=thresholds,
        output_dir=output_dir,
    )


def write_plan_files(scenario: Scenario) -> tuple[Path, Path]:
    """Write reproducible JSON and Markdown plan artifacts for a scenario."""

    scenario.output_dir.mkdir(parents=True, exist_ok=True)
    payload = scenario.plan_payload()
    json_path = scenario.output_dir / f"{scenario.name}-plan.json"
    markdown_path = scenario.output_dir / f"{scenario.name}-plan.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_plan_markdown(scenario), encoding="utf-8")
    return json_path, markdown_path


def render_plan_markdown(scenario: Scenario) -> str:
    """Render a human-readable matrix plan."""

    lines = [
        f"# Performance Matrix: {scenario.name}",
        "",
        scenario.description,
        "",
        "## Target",
        "",
        f"- URL: `{scenario.url}`",
        f"- Organisations: {', '.join(org.name for org in scenario.organisations)}",
        "- API keys are read from environment variables and are not written to artifacts.",
        "",
        "## Breakpoint Thresholds",
        "",
        f"- Max failure rate: `{scenario.thresholds.max_failure_rate:.4f}`",
        f"- Max p95 latency: `{scenario.thresholds.max_p95_ms:.0f} ms`",
        f"- Max p99 latency: `{scenario.thresholds.max_p99_ms:.0f} ms`",
        "",
        "## Matrix Rows",
        "",
        "| Row | Rules | Mode | Profile | Complexity | RPS | Duration | Concurrency |",
        "| --- | ---: | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in scenario.rows():
        lines.append(
            "| "
            f"`{row.row_id}` | {row.rule_count} | `{row.execution_mode}` | `{row.match_profile}` | "
            f"`{row.rule_complexity}` | {row.step.target_rps:g} | {row.step.duration_seconds}s | "
            f"{row.step.concurrency} |"
        )
    lines.extend(
        [
            "",
            "## Required Target Setup",
            "",
            "Before running a row, configure each target organisation to match the row labels:",
            "",
            "- active main-rule count equals the row's `Rules` value",
            "- `main_rule_execution_mode` equals the row's `Mode` value",
            "- seeded rules and payloads match the row's `Profile` and `Complexity` intent",
            "",
        ]
    )
    return "\n".join(lines)


def _load_organisations(value: Any) -> list[OrganisationTarget]:
    if not isinstance(value, list):
        raise ValueError("organisations must be a list.")
    organisations: list[OrganisationTarget] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each organisation must be a mapping.")
        organisations.append(
            OrganisationTarget(
                name=_required_str(item, "name"),
                api_key_env=_required_str(item, "api_key_env"),
                weight=int(item.get("weight", 1)),
            )
        )
    if any(org.weight < 1 for org in organisations):
        raise ValueError("Organisation weights must be positive integers.")
    return organisations


def _load_workload(value: Any) -> list[WorkloadStep]:
    if not isinstance(value, list):
        raise ValueError("workload must be a list.")
    workload: list[WorkloadStep] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each workload step must be a mapping.")
        step = WorkloadStep(
            name=_required_str(item, "name"),
            target_rps=float(item.get("target_rps", 1.0)),
            duration_seconds=int(item.get("duration_seconds", 60)),
            warmup_seconds=int(item.get("warmup_seconds", 0)),
            concurrency=int(item.get("concurrency", 1)),
        )
        if step.target_rps <= 0:
            raise ValueError("target_rps must be greater than zero.")
        if step.duration_seconds < 1:
            raise ValueError("duration_seconds must be at least one.")
        if step.warmup_seconds < 0:
            raise ValueError("warmup_seconds cannot be negative.")
        if step.concurrency < 1:
            raise ValueError("concurrency must be at least one.")
        workload.append(step)
    return workload


def _required_str(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string field: {key}")
    return value.strip()


def _required_str_list(mapping: dict[str, Any], key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Missing required list field: {key}")
    values = [str(item).strip() for item in value]
    if any(not item for item in values):
        raise ValueError(f"{key} cannot contain blank values.")
    return values


def _required_int_list(mapping: dict[str, Any], key: str) -> list[int]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Missing required list field: {key}")
    values = [int(item) for item in value]
    if any(item < 0 for item in values):
        raise ValueError(f"{key} cannot contain negative values.")
    return values
