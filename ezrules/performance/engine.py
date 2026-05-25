from __future__ import annotations

import time
from dataclasses import dataclass

from ezrules.core.rule_engine import (
    RULE_EXECUTION_MODE_ALL_MATCHES,
    RULE_EXECUTION_MODE_FIRST_MATCH,
    RuleEngine,
    RuleEngineFactory,
)
from ezrules.core.user_lists import AbstractUserListManager
from ezrules.demo_data import USER_LISTS
from ezrules.performance.events import build_event_data
from ezrules.performance.rules import build_performance_rules


@dataclass(frozen=True, slots=True)
class EngineTimingResult:
    iterations: int
    total_seconds: float
    evaluations_per_second: float
    latency_min_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_max_ms: float


class PerformanceListManager(AbstractUserListManager):
    """Static list provider for in-process performance rule compilation."""

    def __init__(self) -> None:
        self.lists = {
            "MiddleAsiaCountries": ["KZ", "UZ", "KG", "TJ", "TM"],
            "NACountries": ["CA", "US", "MX", "GL"],
            "LatamCountries": [
                "AR",
                "BO",
                "BR",
                "CL",
                "CO",
                "CR",
                "CU",
                "DO",
                "EC",
                "SV",
                "GT",
                "HN",
                "MX",
                "NI",
                "PA",
                "PY",
                "PE",
                "PR",
                "UY",
                "VE",
            ],
            **USER_LISTS,
        }

    def add_entry(self, list_name: str, new_entry: str) -> None:
        self.lists.setdefault(list_name, []).append(new_entry)

    def get_entries(self, list_name: str) -> list[str]:
        return self.lists[list_name]

    def get_all_entries(self) -> dict[str, list[str]]:
        return self.lists

    def remove_entry(self, list_name: str, entry_value: str) -> None:
        if list_name in self.lists:
            self.lists[list_name] = [entry for entry in self.lists[list_name] if entry != entry_value]

    def create_list(self, list_name: str) -> None:
        self.lists.setdefault(list_name, [])

    def delete_list(self, list_name: str) -> None:
        self.lists.pop(list_name, None)


def build_rule_engine(
    *,
    rule_count: int,
    execution_mode: str,
    rule_complexity: str = "demo_scalar_and_nested",
) -> RuleEngine:
    """Build a pure Python rule engine matching a matrix row."""

    if execution_mode not in {RULE_EXECUTION_MODE_ALL_MATCHES, RULE_EXECUTION_MODE_FIRST_MATCH}:
        raise ValueError(f"Unknown execution mode: {execution_mode}")
    rules = [
        {
            "rid": rule.rid,
            "r_id": index,
            "logic": rule.logic,
            "description": rule.description,
        }
        for index, rule in enumerate(
            build_performance_rules(rule_count=rule_count, rule_complexity=rule_complexity),
            start=1,
        )
    ]
    return RuleEngineFactory.from_json(
        rules,
        list_values_provider=PerformanceListManager(),
        execution_mode=execution_mode,
    )


def time_rule_engine(
    *,
    rule_count: int,
    execution_mode: str,
    match_profile: str,
    rule_complexity: str = "demo_scalar_and_nested",
    iterations: int,
) -> EngineTimingResult:
    """Time in-process rule evaluation without HTTP, auth, or database writes."""

    engine = build_rule_engine(
        rule_count=rule_count,
        execution_mode=execution_mode,
        rule_complexity=rule_complexity,
    )
    events = [build_event_data(match_profile=match_profile, seed=index) for index in range(iterations)]
    latencies: list[float] = []
    started = time.perf_counter()
    for event_data in events:
        request_started = time.perf_counter()
        engine(event_data)
        latencies.append((time.perf_counter() - request_started) * 1000)
    total_seconds = time.perf_counter() - started
    sorted_latencies = sorted(latencies)
    return EngineTimingResult(
        iterations=iterations,
        total_seconds=total_seconds,
        evaluations_per_second=iterations / total_seconds if total_seconds > 0 else 0.0,
        latency_min_ms=sorted_latencies[0],
        latency_p50_ms=_percentile(sorted_latencies, 50),
        latency_p95_ms=_percentile(sorted_latencies, 95),
        latency_p99_ms=_percentile(sorted_latencies, 99),
        latency_max_ms=sorted_latencies[-1],
    )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        raise ValueError("Cannot compute percentile for an empty list.")
    if len(values) == 1:
        return values[0]
    index = round((percentile / 100) * (len(values) - 1))
    return values[index]
