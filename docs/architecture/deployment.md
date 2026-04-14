# Deployment Guide

This page describes the deployment topology that matches the current repository.

For system boundaries and design rationale, use [Architecture Overview](overview.md).
For environment variable details, use [Configuration](../getting-started/configuration.md).

---

## ECS/Fargate Example

This section documents one AWS ECS/Fargate deployment shape for ezrules. It is a reference topology, not a requirement for all deployments or self-hosted users.

The application runtime is split across these services/tasks:

| Runtime | Responsibility |
|---|---|
| `frontend` | Serves the Angular SPA |
| `api` | Runs `uv run ezrules api --port 8888` for manager APIs and `/api/v2/evaluate` |
| `celery-worker` | Runs `uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo` for backtesting jobs |
| `celery-beat` | Runs `uv run celery -A ezrules.backend.tasks beat -l INFO` for field-observation and shadow drain schedules |
| `init` / migration task | One-shot task that runs schema setup, Alembic migrations, and initial org bootstrap before services start |

Required backing services:

| Dependency | Purpose |
|---|---|
| PostgreSQL | Source of truth for rules, auth, outcomes, audit history, and analytics data |
| Redis | Celery broker plus the default queue backing store for async field-observation and shadow drains |

---

## Public Routing

Use same-origin browser routing by default.

Recommended ALB routing:

| Path | Target |
|---|---|
| `/*` | `frontend` service |
| `/api/*` | `api` service |
| `/docs` | `api` service |
| `/redoc` | `api` service |
| `/openapi.json` | `api` service |
| `/ping` | `api` service |

Why this is the default:

- the production frontend build now defaults to same-origin API requests
- browser auth, cookies, and refresh flows stay on one public origin
- no explicit CORS configuration is needed for the main UI path

If you intentionally split frontend and API across different public origins:

1. Build the frontend image with `EZRULES_FRONTEND_API_URL=https://api.example.com`.
2. Set `EZRULES_CORS_ALLOWED_ORIGINS=https://app.example.com` on the API task.
3. Use `EZRULES_CORS_ALLOW_ORIGIN_REGEX` only when a fixed allowlist is not practical.

---

## ECS Runtime Contract

Minimum task/service contract:

- `frontend` can be scaled independently from the API
- `api` must have network access to PostgreSQL and Redis
- `celery-worker` must share the same code image and runtime env as `api`, plus broker connectivity
- `celery-beat` must share the same code image and runtime env as `api`, plus broker connectivity
- `init` must run to completion before `api`, `celery-worker`, and `celery-beat` are treated as ready

Minimum environment inputs:

- `EZRULES_DB_ENDPOINT`
- `EZRULES_APP_SECRET`
- `EZRULES_CELERY_BROKER_URL`
- `EZRULES_APP_BASE_URL`
- optional SMTP settings if invite/reset emails should leave the environment
- optional `EZRULES_CORS_ALLOWED_ORIGINS` / `EZRULES_CORS_ALLOW_ORIGIN_REGEX` only for split-origin deployments

Recommended production rollout sequence:

1. Run the `init` task against the target database.
2. Deploy or update the `api` service.
3. Deploy or update `celery-worker`.
4. Deploy or update `celery-beat`.
5. Deploy or update `frontend`.
6. Verify `/ping`, login, a sample `/api/v2/evaluate` request, and one async queue-driven flow.

---

## Local Validation Modes

The repository still ships local Docker setups for validation and development.

### Demo stack

Use `docker-compose.demo.yml` when you want a seeded environment:

```bash
docker compose -f docker-compose.demo.yml up --build
```

This starts:

- PostgreSQL
- Redis
- `init`
- `api`
- `celery-worker`
- `celery-beat`
- `frontend`
- Mailpit

The database is recreated from scratch on each full rerun so old schemas do not poison the demo.

### Production-validation stack

Use `docker-compose.prod.yml` to validate the production images and startup sequence locally:

```bash
cp .env.example .env
docker compose -f docker-compose.prod.yml up --build
```

This mirrors the app-level runtime split but remains a single-host Docker setup rather than an ECS deployment.

### Development mode

Use `docker compose up -d` to run infrastructure locally while you keep API and frontend as local dev processes.
That stack now includes both `celery-worker` and `celery-beat` so async queue drains behave like the documented runtime.

---

## Validation Checklist

Use this after any deployment change:

1. `curl http://<api-host>/ping` returns `{"status":"ok"}`.
2. Browser login succeeds through the public frontend.
3. `POST /api/v2/evaluate` succeeds with a valid API key or Bearer token.
4. A queued backtest can move beyond `PENDING`.
5. Shadow/field-observation drains keep progressing, confirming `celery-beat` is alive.

---

## Follow-Up Infra Work

This repository now documents the correct app/runtime topology, but infra implementation is still external work.

Typical follow-up items:

- ECS task definitions and service autoscaling policies
- ALB listeners, target groups, and TLS certificates
- secrets delivery for app/API/SMTP credentials
- RDS PostgreSQL and Redis provisioning
- logging, metrics, and alerting for `api`, `celery-worker`, and `celery-beat`
