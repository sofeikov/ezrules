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

Run the load generator outside the API host when measuring deployable capacity. Record the API worker count, container CPU and memory limits, Postgres instance size, connection pool settings, Redis/Celery availability, and git SHA alongside the result artifacts.

The starter harness does not create organisations or seed production-like rule sets itself. Use existing admin/API setup or `uv run ezrules generate-random-data --n-rules ... --org-name ...` in controlled non-production environments before running each matrix row.
