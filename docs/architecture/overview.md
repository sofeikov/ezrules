# Architecture Overview

This page describes system boundaries, core components, and key design decisions.
It intentionally avoids deployment runbook detail.

## Scope and Boundaries

In scope:

- API service behavior and boundaries
- data storage model at a high level
- rule evaluation flow
- access-control and audit model

Out of scope:

- step-by-step deployment commands (see [Deployment Guide](deployment.md))
- environment variable tuning (see [Configuration](../getting-started/configuration.md))

---

## System Context

```
Web UI (Angular)  --->  FastAPI service (api/v2 + evaluate)  --->  PostgreSQL
                                   |
                                   +--> Redis/Celery (backtesting tasks)
External systems  --->  POST /api/v2/evaluate
```

Primary runtime boundary:

- `ezrules api` is the main backend process
- rule execution happens inside that backend process

---

## Core Components

| Component | Responsibility | Notes |
|---|---|---|
| FastAPI service | Serves API v2 endpoints and evaluator endpoint | Stateless app process |
| Rule engine | Executes active rules against incoming event payloads | Uses configured rules and persists evaluation output |
| PostgreSQL | Stores rules, outcomes, events, labels, users, and audit history | Source of truth |
| Celery worker (optional) | Executes async backtesting jobs | Uses Redis broker |
| Angular frontend | Operator/analyst/admin UI | Connects to API v2 |

---

## Data Model Areas

High-level storage domains:

- Rules/config history: `rules`, `rules_history`, `rule_engine_config`, `rule_engine_config_history`
- Event evaluation: `testing_record_log`, `testing_results_log`
- Decision controls: `allowed_outcomes`, `event_labels`, user list tables
- Access control: `user`, `role`, `roles_users`, `actions`, `role_actions`
- Audit history: rule/config/user-list/outcome/label history tables

---

## Key Flows

### 1) Event Evaluation Flow

1. Caller sends `POST /api/v2/evaluate`
2. API validates payload
3. Active rule configuration is loaded/executed
4. Outcomes are aggregated (`rule_results`, `outcome_counters`, `outcome_set`)
5. Evaluation data is stored in DB
6. Response returned to caller

### 2) Rule Lifecycle Flow

1. User creates/updates rule via API/UI
2. Rule change is persisted
3. Rule/config history entries are captured with `changed_by` attribution
4. Updated rules become part of subsequent evaluations

### 3) Label Feedback Flow

1. Labels are applied via API (`mark-event` or upload)
2. Label data is stored
3. Analytics endpoints aggregate outcomes/labels for UI charts

---

## Key Design Decisions and Tradeoffs

| Decision | Why | Tradeoff |
|---|---|---|
| Unified API service for management + evaluation | Simplifies local/dev topology and operations | One service handles mixed workloads |
| Evaluate endpoint without built-in user auth | Supports internal service-to-service usage | Must enforce network-level controls externally |
| Rule execution in-process | Low integration overhead and direct access to model context | Poorly written rules can impact latency |
| PostgreSQL as source of truth | Strong relational model and auditability | Requires schema/index care at larger scale |
| Optional Celery for backtesting | Keeps heavy reprocessing async | Adds Redis/worker operational dependency |

---

## Security Model (High Level)

- JWT auth for most API v2 endpoints
- RBAC permissions enforced at endpoint layer
- Audit history recorded for key mutable resources
- Evaluate endpoint intended for internal/service access; protect it with gateway/network controls

---

## Scalability Model (High Level)

- API service is stateless and can be horizontally scaled
- Database remains central shared state
- Backtesting workload can be scaled by worker capacity

For production sizing, benchmark with your real rule mix and event load.

---

## Extension Points

Common customization directions:

- custom helper functions used by rules
- custom execution wrappers/instrumentation around rule execution
- organization-specific list and outcome governance

Keep extensions observable and testable to avoid hidden runtime risk.

---

## Related Docs

- [Deployment Guide](deployment.md)
- [Configuration](../getting-started/configuration.md)
- [API v2 Reference](../api-reference/manager-api.md)
- [Admin Guide](../user-guide/admin-guide.md)
