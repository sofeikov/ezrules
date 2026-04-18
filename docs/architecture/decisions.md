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

## ADR-006: Document An ECS/Fargate Reference Topology

- **Decision**: document an AWS ECS/Fargate reference topology with distinct `frontend`, `api`, `celery-worker`, `celery-beat`, and init/migration task responsibilities.
- **Why**: this records one production-oriented deployment shape that matches the current unified FastAPI + Celery + PostgreSQL + Redis architecture without prescribing it as the only valid deployment model.
- **Tradeoff**: the repository documents one concrete topology, but users may still choose other hosting approaches and must adapt the same runtime responsibilities there.
- **Related docs**: [Deployment Guide](deployment.md), [Configuration](../getting-started/configuration.md).

## ADR-007: Same-Origin Browser Access By Default

- **Decision**: production frontend builds default to same-origin API requests, with optional explicit CORS configuration only for split-origin deployments.
- **Why**: same-origin ALB routing removes the need for fragile localhost defaults and keeps browser auth flows simple in production.
- **Tradeoff**: split-origin deployments must set both the frontend API URL and backend CORS configuration deliberately.
- **Related docs**: [Deployment Guide](deployment.md), [Configuration](../getting-started/configuration.md).

## ADR-008: Field References Must Stay Canonical Through AST Analysis

- **Decision**: `RuleParamExtractor.visit_Call()` recognizes only the exact helper call shape produced by the `$field.path` compiler rewrite: `__ezrules_lookup__(t, "field.path")`.
- **Why**: extracted field references drive verify warnings, test JSON prefill, and backtesting missing-field eligibility. If call matching were broader, hand-written helper calls or wrapped arguments could masquerade as canonical `$...` references and create bypasses or misleading metadata.
- **Tradeoff**: the internal lookup helper is not public syntax. Only canonical `$...` notation is guaranteed to participate in downstream field-reference analysis.
- **Related docs**: [Creating Rules](../user-guide/creating-rules.md), [Evaluator API](../api-reference/evaluator-api.md), [Complex Entities in Fraud Rules](../blog/complex-entities-in-fraud-rules.md).
