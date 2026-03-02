# Tooling
1. The project uses uv for environment and package management. Only use uv for Python-related package management. Never create virtual environments manually.
2. Code quality checks: `uv run poe check` (ruff format check, ty type check, ruff linting).
3. CLI test helper: `./test_cli.sh`.

# Backend Tests (Canonical)
Use this as the single source of truth for backend test runs.

## Preconditions
- PostgreSQL must be reachable on `localhost:5432`.
- Default local stack (`docker-compose.yml`) uses `postgres:root`.
- Test DB name should be `tests`.

## Full backend suite command
```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests \
EZRULES_TESTING=true \
EZRULES_APP_SECRET=test-secret \
EZRULES_ORG_ID=1 \
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```

## Notes
- `conftest.py` creates/drops the `tests` database and applies Alembic migrations (`upgrade head`) before tests.
- If another Postgres container is bound to `5432` with different credentials, override `EZRULES_DB_ENDPOINT` accordingly.
- If uv cache permission errors occur in restricted environments, prefix with `UV_CACHE_DIR=/tmp/uv-cache`.
- CI parity sequence is: `uv sync --dev` -> `uv run alembic upgrade head` -> pytest command above.

# Common Development Commands
- **Install dependencies**: `uv sync`
- **Initialize database**: `uv run ezrules init-db`
- **Add user**: `uv run ezrules add-user --user-email admin@example.com --password admin`
- **Start API service** (FastAPI, includes evaluator): `uv run ezrules api --port 8888`
- **Start Celery worker** (required for backtesting): `uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo`
- **Generate test data**: `uv run ezrules generate-random-data --n-rules 10 --n-events 100`

# VS Code Launch Configs (.vscode/launch.json)
All common operations are available as VS Code launch configs; use these instead of manual commands where possible:
- **Reset Dev Environment**: recreates dev DB (`ezrules`), adds admin user, generates fake data.
  Equivalent CLI: `EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules EZRULES_TESTING=true uv run ezrules reset-dev`
- **Init db with autodelete**: drops/recreates dev DB schema only.
  Equivalent CLI: `EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules EZRULES_TESTING=true uv run ezrules init-db --auto-delete`
- **API v2 (FastAPI)**: starts API on port 8888 with reload
- **Tests**: runs full pytest suite with coverage (test DB)
- **Celery Worker**, **Generate Fake Data**, **Playwright: Debug** are also available

# Architecture Overview
ezrules is a transaction monitoring engine with business rule capabilities.

## Core Components
- **ezrules.core**: rule engine, rule management, outcomes processing, user lists
- **ezrules.backend**: FastAPI v2 API (includes evaluator), rule executors
- **ezrules.models**: SQLAlchemy models, including audit/history tables
- **ezrules.cli**: CLI for DB operations and data generation

## Services Architecture
- **API v2 Service** (port 8888): FastAPI service for Angular frontend and rule evaluation
- **Database Layer**: PostgreSQL with SQLAlchemy ORM and explicit audit/history tables

## Data Flow
1. Events submitted to API service (`POST /api/v2/evaluate`)
2. Rules executed against event data using rule executors
3. Outcomes aggregated and stored
4. Results available via API and web interface

# Writing New Code
1. Never modify test files unless explicitly allowed.
2. **BEFORE RUNNING ANY TESTS**: Ask the user if they want tests to be run. Tests can take significant time. If you do run the tests, make sure you run production grade serving on the backend, otherwise playwright tests will overwhel mthe dev server
3. Before reporting task completion, ensure `uv run poe check` completes successfully.
4. Any new imports must go to the top of the file (no inline imports in functions).
5. Any new functionality must be covered with tests.
6. **FOR ANGULAR FRONTEND CHANGES**: Any new pages/navigation must have Playwright e2e tests in `ezrules/frontend/e2e/tests/` plus corresponding page objects in `e2e/pages/*.page.ts`.
7. If a new endpoint is implemented, restart the API server if needed.
8. If one e2e test fails, stop and fix the root cause before waiting for all failures.
9. Database-related functionality must be tested on the live test DB rather than mocked.
10. If functionality affects user experience/actions, update README and `docs/whatsnew.md`.
11. When tests are approved, run ALL tests, not selective subsets.
12. After tests are done, kill API server (8888) and Angular dev server (4200) if you started them manually.

# Writing New Documentation
1. Canonical documentation map: [DOCUMENTATION_MAP.md](DOCUMENTATION_MAP.md)
2. The project uses MkDocs (`docs/` + `mkdocs.yml`)
3. Build docs with `uv run mkdocs build --strict`
4. If backend endpoints/schemas/auth/error contracts change, update:
   - `docs/api-reference/manager-api.md`
   - `docs/api-reference/evaluator-api.md` (if evaluate flow changed)
   - related how-to pages (`docs/getting-started/integration-quickstart.md`, `docs/troubleshooting.md`, relevant user guides)
5. If Angular routes/features/env keys change, update:
   - `docs/getting-started/quickstart.md`
   - relevant user guide pages
   - `docs/getting-started/configuration.md` (if env usage changed)
6. If runtime commands/env vars change, update:
   - `docs/getting-started/installation.md`
   - `docs/getting-started/configuration.md`
   - `docs/architecture/deployment.md`
7. Update README and `docs/whatsnew.md` for user-facing changes
8. Snippet includes live in `docs/snippets/*.txt`; keep include paths aligned
9. Be factual; only write sections that can be backed by code
