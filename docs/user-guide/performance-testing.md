# Performance Testing

ezrules includes an initial performance matrix harness for finding where a deployable evaluator setup starts to break down.

The harness treats multiple clients as multiple organisations. Each organisation is represented by its own evaluator API key, and the runner distributes traffic across those keys according to the scenario weights.

## Measurement Layers

Use two layers for the same matrix labels.

The pure Python rule-engine layer executes generated rules in-process:

```bash
uv run python -m ezrules.performance.runner engine performance/scenarios/initial-breakpoint.yaml \
  --row-filter "rules-250__mode-first_match" \
  --iterations 5000
```

This measures only rule compilation/execution behavior. It does not include HTTP, authentication, database locks, writes, observations, alerts, rollout logs, shadow enqueueing, or network overhead.

The API ingestion layer targets the real evaluator path:

```bash
uv run python -m ezrules.performance.runner run performance/scenarios/initial-breakpoint.yaml \
  --row-filter "rules-250__mode-first_match"
```

Compare the two layers for the same row. The difference between API latency and pure engine latency is the platform overhead from service and persistence work.

For routine local API benchmarking, prefer the local API suite runner:

```bash
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --workers 4 \
  --continue-after-breach
```

This command creates disposable Docker Postgres and Redis containers, initializes a private database, bootstraps the scenario organisations, generates API keys, seeds each configured rule-count/complexity block, switches `main_rule_execution_mode` for each mode block, starts the API with production-like settings, samples API/Postgres/Redis resources, and writes JSON/Markdown/CSV artifacts under `artifacts/performance/`.

## What API Runs Measure

```bash
POST /api/v2/evaluate
```

That means results include authentication, field normalization, rule execution, event-version persistence, served-decision persistence, per-rule result writes, field observations, alert enqueueing, and rollout or shadow side effects that are enabled in the target environment.

## Initial Scenario

The starter matrix lives at:

```bash
performance/scenarios/initial-breakpoint.yaml
```

It varies:

- active rule count
- `main_rule_execution_mode`
- rule complexity profile
- event risk/match profile
- request rate and concurrency
- organisation/API-key distribution

Before running a row, configure each target organisation to match the row labels. For example, if the row says `rules-250__mode-first_match`, seed 250 active main rules for each target organisation and set `main_rule_execution_mode=first_match`.

## Write A Plan

Generate reproducible plan artifacts without sending traffic:

```bash
uv run python -m ezrules.performance.runner plan performance/scenarios/initial-breakpoint.yaml
```

This writes JSON and Markdown under `artifacts/performance/`.

## Run Against A Target

Set one API key per target organisation:

```bash
export EZRULES_PERF_ORG_A_API_KEY=...
export EZRULES_PERF_ORG_B_API_KEY=...
```

Then run the API ingestion matrix:

```bash
uv run python -m ezrules.performance.runner run performance/scenarios/initial-breakpoint.yaml
```

To run one slice:

```bash
uv run python -m ezrules.performance.runner run performance/scenarios/initial-breakpoint.yaml \
  --row-filter "rules-250__mode-first_match"
```

By default, the runner stops after the first threshold breach. Use `--continue-after-breach` when you want every row to run even after the target is already failing the configured limits.

## Run The Local API Suite

The `api-suite` command is the repeatable local workflow for finding the current API breakpoint. It owns target setup, so row labels such as `rules-250__mode-first_match` match the actual local target state.

```bash
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --workers 4 \
  --api-port 18888 \
  --postgres-port 55432 \
  --redis-port 56379 \
  --seed-events 100 \
  --continue-after-breach
```

By default the suite:

- uses Docker `postgres:16.0-alpine3.18` with `pg_stat_statements` and `track_io_timing`
- uses Docker `redis:7-alpine`
- runs the API with `EZRULES_TESTING=false`
- starts Uvicorn with `--no-access-log` so terminal logging does not distort high-RPS rows
- removes the local Docker containers when the run finishes

Useful options:

```bash
# Run one matrix slice while iterating.
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --row-filter "rules-50__mode-all_matches__profile-low_risk__complexity-demo_scalar_and_nested__load-smoke"

# Leave containers behind for manual inspection.
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --keep-containers

# Keep access logs only if log throughput is part of the test.
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --access-log
```

### Quick Confirmation Runs

Use the tracked `performance/scenarios/initial-breakpoint.yaml` file for repeatable checks. Files under `artifacts/performance/` are generated run outputs and should not be treated as canonical scenarios.

To confirm the 50-rule, 250 RPS first-match slice that exercises the current high-throughput API path:

```bash
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --workers 4 \
  --api-port 18888 \
  --postgres-port 55432 \
  --redis-port 56379 \
  --seed-events 100 \
  --row-filter "rules-50__mode-first_match__profile-payout__complexity-demo_scalar_and_nested__load-ramp-250" \
  --continue-after-breach
```

To rerun the lower 50-rule, 25 RPS all-matches sanity slice from the same tracked matrix:

```bash
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --workers 4 \
  --api-port 18888 \
  --postgres-port 55432 \
  --redis-port 56379 \
  --seed-events 100 \
  --row-filter "rules-50__mode-all_matches__profile-low_risk__complexity-demo_scalar_and_nested__load-ramp-25" \
  --continue-after-breach
```

Use a unique `--run-id` when comparing repeated local runs so artifact names do not collide:

```bash
uv run python -m ezrules.performance.runner api-suite performance/scenarios/initial-breakpoint.yaml \
  --run-id "$(date -u +%Y%m%d%H%M%S)-rps250-confirm" \
  --row-filter "rules-50__mode-first_match__profile-payout__complexity-demo_scalar_and_nested__load-ramp-250"
```

The suite writes:

- combined JSON results
- combined Markdown summary
- resource and database wait-state samples CSV
- API server log

These outputs are generated artifacts and should not be committed. Communicate headline numbers and caveats in the PR body instead.

## Breakpoint Criteria

A row breaches when any configured threshold is exceeded:

- failure rate
- p95 latency
- p99 latency

The initial thresholds are intentionally conservative:

- failure rate greater than `0.1%`
- p95 greater than `500 ms`
- p99 greater than `1000 ms`

Adjust these in the scenario file to match the service-level target for the deployment.

## Result Artifacts

Each run writes:

- a JSON result file for comparison and automation
- a Markdown summary for review

The JSON includes the scenario plan, per-row throughput, latency percentiles, status-code counts, first error sample, and threshold breaches. API key values are never written to artifacts.

## Deployment Notes

Run the load generator outside the API host when measuring deployable capacity. Record the API worker count, container CPU and memory limits, Postgres instance size, connection pool settings, Redis/Celery availability, logging configuration, rule complexity profile, and git SHA alongside the result artifacts.

The lower-level `run` command does not create organisations or seed production-like rule sets itself. Use `api-suite` for repeatable local runs, or use existing admin/API setup plus `uv run ezrules generate-random-data --n-rules ... --rule-complexity demo_scalar_and_nested --org-name ...` in controlled non-production environments before running lower-level API rows.
