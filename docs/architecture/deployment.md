# Deployment Guide

This guide focuses on a practical local setup using Docker Compose for infrastructure and a local API process.

---

## What Runs Where

- Docker Compose runs:
  - PostgreSQL (`localhost:5432`)
  - Redis (`localhost:6379`)
  - Celery worker (for backtesting tasks)
- Local process runs:
  - FastAPI service (`localhost:8888`)
  - Frontend dev server (`localhost:4200`)

This matches the current project setup and is the fastest path for development/testing.

---

## Prerequisites

- Docker and Docker Compose
- Python 3.12+
- `uv`

---

## 1. Start Infrastructure

From the repository root:

```bash
docker compose up -d
```

This starts Postgres, Redis, and the worker container.

To stop:

```bash
docker compose down        # keep volumes
docker compose down -v     # remove volumes
```

---

## 2. Install Dependencies

```bash
uv sync
```

---

## 3. Initialize Database and Permissions

```bash
uv run ezrules init-db
uv run ezrules init-permissions
```

Create a local user:

```bash
uv run ezrules add-user --user-email admin@example.com --password admin
```

---

## 4. Run API Service

```bash
uv run ezrules api --port 8888
```

Optional (development reload):

```bash
uv run ezrules api --port 8888 --reload
```

---

## 5. Run Frontend (Optional for UI Work)

```bash
cd ezrules/frontend
npm install
npm start
```

The frontend runs on `http://localhost:4200` and connects to the API on `http://localhost:8888`.

For a production-style frontend build:

```bash
cd ezrules/frontend
npm install
npm run build
```

Build output is written to `ezrules/frontend/dist/`.

---

## 6. Verify Service

- API root: `http://localhost:8888/`
- Health check: `http://localhost:8888/ping`
- OpenAPI docs (Swagger UI): `http://localhost:8888/docs`
- ReDoc: `http://localhost:8888/redoc`
- OpenAPI JSON: `http://localhost:8888/openapi.json`
- Frontend UI (dev): `http://localhost:4200`

---

## Backtesting Notes

- Backtesting endpoints enqueue Celery tasks.
- The worker must be running, otherwise tasks stay `PENDING`.
- With `docker compose up -d`, the worker is already running.

---

## Common Local Commands

```bash
# Start infra
docker compose up -d

# Run API
uv run ezrules api --port 8888

# Run checks
uv run poe check

# Run backend tests
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```
