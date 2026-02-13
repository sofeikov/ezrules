# Deployment Guide (Local Runbook)

This runbook covers a practical local deployment model: Docker Compose for infrastructure and local processes for API/frontend.

Use this page for local development and test environments.  
For system boundaries and design rationale, use [Architecture Overview](overview.md).  
For environment variable details, use [Configuration](../getting-started/configuration.md).

---

## Scope

In scope:

- single-host local setup
- API service startup and verification
- optional frontend startup
- backtesting worker readiness

Out of scope:

- production topology design
- cloud platform-specific deployment automation

---

## What Runs Where

- Docker Compose runs:
  - PostgreSQL (`localhost:5432`)
  - Redis (`localhost:6379`)
  - Celery worker (for backtesting tasks)
- Local process runs:
  - FastAPI service (`localhost:8888`)
  - Frontend dev server (`localhost:4200`, optional)

---

## Preflight Checklist

- Docker and Docker Compose installed
- Python 3.12+ installed
- `uv` installed
- Repo cloned and `settings.env` prepared
- Required ports free: `5432`, `6379`, `8888` (and `4200` for frontend)

---

## 1. Start Infrastructure

### Action

```bash
docker compose up -d
```

### Expected

- `docker compose ps` shows PostgreSQL, Redis, and worker containers as `Up`

### Rollback

```bash
docker compose down        # keep volumes
docker compose down -v     # remove volumes
```

---

## 2. Install Dependencies

### Action

```bash
uv sync
```

### Expected

- `uv` completes without dependency resolution errors

### Rollback

- Re-run `uv sync` after fixing dependency/toolchain errors

---

## 3. Initialize Database and Permissions

### Action

```bash
uv run ezrules init-db
uv run ezrules init-permissions
uv run ezrules add-user --user-email admin@example.com --password admin
```

### Expected

- Commands complete without DB/auth errors
- Admin user can log in later via UI/API

### Rollback

- Fix DB endpoint/credentials in `settings.env`
- Re-run initialization commands

---

## 4. Run API Service

### Action

--8<-- "snippets/start-api.md"

Optional (development reload):

```bash
uv run ezrules api --port 8888 --reload
```

### Expected

- `http://localhost:8888/ping` responds
- OpenAPI docs load at `http://localhost:8888/docs`

### Rollback

- Stop API process
- Free conflicting port or run on a different port

---

## 5. Run Frontend (Optional for UI Work)

### Action

```bash
cd ezrules/frontend
npm install
npm start
```

### Expected

- Frontend loads at `http://localhost:4200`
- Login flow can reach backend at `http://localhost:8888`

### Rollback

- Stop frontend process
- Fix Node/npm dependency issues, then restart

---

## 6. Verify Service

- API root: `http://localhost:8888/`
- Health check: `http://localhost:8888/ping`
- OpenAPI docs:
  - Swagger UI: `http://localhost:8888/docs`
  - ReDoc: `http://localhost:8888/redoc`
  - OpenAPI JSON: `http://localhost:8888/openapi.json`
- Frontend UI (dev): `http://localhost:4200` (if started)

---

## Common Failure Modes

| Symptom | Likely Cause | Action |
|---|---|---|
| API fails to start | DB endpoint invalid or DB down | Check `settings.env`, then `docker compose ps` |
| API port conflict | Port `8888` already in use | Stop conflicting process or change API port |
| Backtests stay `PENDING` | Worker or Redis unavailable | Confirm compose services are `Up` |
| Frontend cannot log in | API not reachable/auth user missing | Verify API health and recreate admin user |

---

## Backtesting Notes

- Backtesting endpoints enqueue Celery tasks
- Worker must be running, or tasks remain `PENDING`
- `docker compose up -d` already starts worker in this local model

---

## Clean Shutdown

Stop local frontend/API processes (if running), then:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to remove local volumes/data.

---

## Common Local Commands

```bash
docker compose up -d
uv run ezrules api --port 8888
uv run poe check
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```
