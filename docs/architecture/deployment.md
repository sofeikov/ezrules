# Deployment Guide (Local Runbook)

This runbook covers local deployment. Three modes are supported.

For system boundaries and design rationale, use [Architecture Overview](overview.md).
For environment variable details, use [Configuration](../getting-started/configuration.md).

---

## Scope

In scope:

- single-host local setup, all three deployment modes
- API service startup and verification
- backtesting worker readiness

Out of scope:

- production topology design
- cloud platform-specific deployment automation

---

## Deployment Modes

### Mode 1 — Full Docker (demo or production)

Everything runs inside Docker. No local Python or Node required.

| Container | What it does |
|---|---|
| `postgres` | Database (`5432` not exposed to host by default) |
| `redis` | Celery broker (`6379` not exposed to host by default) |
| `init` | One-shot: creates DB schema, admin user, optional seed data |
| `api` | FastAPI service on `localhost:8888` |
| `worker` | Celery worker for backtesting |
| `frontend` | nginx serving the Angular SPA on `localhost:4200` |

**Demo** (pre-seeded with sample rules and events):

```bash
docker compose -f docker-compose.demo.yml up --build
```

**Production** (empty database, credentials from `.env`):

```bash
cp .env.example .env   # fill in APP_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose -f docker-compose.prod.yml up --build
```

Verify:

```bash
curl http://localhost:8888/ping        # → {"status":"ok"}
# open http://localhost:4200 in a browser
```

Stop (keep data):

```bash
docker compose -f docker-compose.demo.yml down
# or
docker compose -f docker-compose.prod.yml down
```

Stop and delete all data:

```bash
docker compose -f docker-compose.demo.yml down -v
```

---

### Mode 2 — Development (infrastructure in Docker, services local)

PostgreSQL, Redis, and the Celery worker run in Docker. The API and Angular dev server run as local processes, enabling hot-reload and debugger attachment.

**What runs where:**

- Docker: PostgreSQL (`localhost:5432`), Redis (`localhost:6379`), Celery worker
- Local: FastAPI (`localhost:8888`), Angular dev server (`localhost:4200`)

**Preflight:** Docker, Python 3.12+, `uv`, Node 20+, ports `5432 6379 8888 4200` free.

#### 1. Start infrastructure

```bash
docker compose up -d
```

Expected: `docker compose ps` shows postgres, redis, worker as `Up`.

Rollback:

```bash
docker compose down        # keep volumes
docker compose down -v     # remove volumes
```

#### 2. Install dependencies

```bash
uv sync
```

#### 3. Initialize database

```bash
uv run ezrules init-db
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

Requires `settings.env` with `EZRULES_DB_ENDPOINT`, `EZRULES_APP_SECRET`, `EZRULES_ORG_ID`.

#### 4. Run API

--8<-- "snippets/start-api.md"

Optional (with auto-reload):

```bash
uv run ezrules api --port 8888 --reload
```

Expected: `http://localhost:8888/ping` responds.

#### 5. Run frontend

```bash
cd ezrules/frontend
npm install
npm start
```

Expected: `http://localhost:4200` loads login page.

#### 6. Verify

- Health check: `http://localhost:8888/ping`
- OpenAPI: `http://localhost:8888/docs`
- Frontend: `http://localhost:4200`

#### Clean shutdown

Stop local processes, then:

```bash
docker compose down
```

---

## Common Failure Modes

| Symptom | Likely Cause | Action |
|---|---|---|
| `init` container exits non-zero | DB not ready or env var missing | Check `docker compose logs init` |
| API fails to start | DB endpoint invalid or DB down | Check `settings.env`, then `docker compose ps` |
| Port `8888` or `4200` conflict | Another process holds the port | `lsof -i :8888` to identify, then stop it |
| Backtests stay `PENDING` | Worker or Redis unavailable | `docker compose ps` — confirm worker is `Up` |
| Frontend cannot log in | API not reachable or no admin user | Verify `/ping`, re-run `add-user` |

---

## Backtesting Notes

- Backtesting enqueues Celery tasks via Redis
- Worker must be running or tasks remain `PENDING` indefinitely
- All three deployment modes include a running worker

---

## Common Development Commands

```bash
docker compose up -d
uv run ezrules api --port 8888
uv run poe check
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```
