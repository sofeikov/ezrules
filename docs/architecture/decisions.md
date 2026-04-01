# Architecture Decisions

This page captures the major architecture decisions currently reflected in the codebase.
Use it as the canonical decision log until formal ADR files are introduced.

## ADR-001: Unified API Service

- **Decision**: Run management APIs and evaluator endpoint in one FastAPI service (`uv run ezrules api`).
- **Why**: simpler deployment topology and fewer cross-service failure modes.
- **Tradeoff**: mixed workloads share the same process and resource pool.
- **Related docs**: [Architecture Overview](overview.md), [API v2 Reference](../api-reference/manager-api.md).

## ADR-002: Internal-Use Evaluator Endpoint

- **Decision**: keep `POST /api/v2/evaluate` inside the unified API service and require either an API key or a Bearer token.
- **Why**: supports service-to-service evaluation without a separate evaluator service while preserving organisation scoping.
- **Tradeoff**: callers must provision and manage credentials for every request.
- **Related docs**: [Evaluator API](../api-reference/evaluator-api.md), [Architecture Overview](overview.md).

## ADR-003: PostgreSQL as Source of Truth

- **Decision**: persist rules, outcomes, labels, user lists, users/roles, and audit history in PostgreSQL.
- **Why**: strong consistency and auditability for operational workflows.
- **Tradeoff**: schema/index tuning is required as data volume grows.
- **Related docs**: [Architecture Overview](overview.md), [Configuration](../getting-started/configuration.md).

## ADR-004: In-Process Rule Execution

- **Decision**: execute rule logic inside the API process.
- **Why**: low integration overhead and immediate access to active configuration.
- **Tradeoff**: expensive rule logic can directly affect API latency.
- **Related docs**: [Creating Rules](../user-guide/creating-rules.md), [Monitoring & Analytics](../user-guide/monitoring.md).

## ADR-005: Async Backtesting via Celery

- **Decision**: execute backtesting jobs asynchronously with Celery workers.
- **Why**: isolates long-running reprocessing from request/response latency.
- **Tradeoff**: introduces Redis/worker operational dependency and queue management.
- **Related docs**: [Admin Guide](../user-guide/admin-guide.md), [Deployment Guide](deployment.md).
