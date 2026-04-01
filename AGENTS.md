# Tooling
1. The project uses uv for environment and package management. Only use uv for Python-related package management. Never create virtual environments manually.
2. Code quality checks: `uv run poe check` (ruff format check, ty type check, ruff linting).
3. CLI test helper: `./test_cli.sh`.

# Backend Tests (Canonical)
Use this as the single source of truth for backend test runs.

## Preconditions
- PostgreSQL must be reachable on `localhost:5432`.
- Default local stack (`docker-compose.yml`) uses `postgres:root`.
- For local agent runs, do **not** use the shared `tests` database when other agents may be active. Follow the existing private E2E naming convention instead, for example `tests_e2e_54043`.

## Full backend suite command
```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests_e2e_54043 \
EZRULES_TESTING=true \
EZRULES_APP_SECRET=test-secret \
EZRULES_ORG_ID=1 \
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```

## Notes
- `conftest.py` creates/drops the database named in `EZRULES_DB_ENDPOINT` and applies Alembic migrations (`upgrade head`) before tests.
- When running the full suite locally, always use a private DB name for the backend test run and a different private DB name for any dev/E2E stack. Never reuse shared names like `tests` or `ezrules`.
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
When creating a new git worktree for this repository, copy the root `.vscode/` folder into the new worktree before starting work so all launch/run configurations remain available there.
When working in a new git worktree, proactively ensure dependencies are installed in that worktree before starting: run `uv sync` for Python deps and make sure frontend deps are present in `ezrules/frontend/` (run `npm install` there if `node_modules` is missing) so the user does not have to do manual dependency setup.

All common operations are available as VS Code launch configs; use these instead of manual commands where possible:
- **Reset Dev Environment**: recreates dev DB (`ezrules`), adds admin user, generates fake data.
  Equivalent CLI: `EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules EZRULES_TESTING=true uv run ezrules reset-dev`
- **Init db with autodelete**: drops/recreates dev DB schema only.
  Equivalent CLI: `EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules EZRULES_TESTING=true uv run ezrules init-db --auto-delete`
- **API v2 (FastAPI)**: starts API on port 8888 with reload
- **Tests**: runs full pytest suite with coverage (test DB)
- **Celery Worker**, **Generate Fake Data**, **Playwright: Debug** are also available
- For local full-suite agent runs, override the shared launch-config DB endpoints with private `*_e2e_<suffix>` database names before starting anything.

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
1. You may add new test files without asking. Do not modify existing test files unless explicitly allowed.
2. **BEFORE RUNNING ANY TESTS**: Ask the user if they want tests to be run. Tests can take significant time. If you do run the tests, make sure you run production grade serving on the backend, otherwise playwright tests will overwhel mthe dev server
3. Before reporting task completion, ensure `uv run poe check` completes successfully.
4. Any new imports must go to the top of the file (no inline imports in functions).
5. Any new functionality must be covered with tests.
6. **FOR ANGULAR FRONTEND CHANGES**: Any new pages/navigation must have Playwright e2e tests in `ezrules/frontend/e2e/tests/` plus corresponding page objects in `e2e/pages/*.page.ts`.
7. If a new endpoint is implemented, restart the API server if needed.
8. If one e2e test fails, stop and fix the root cause before waiting for all failures.
9. For Playwright runs that include invite/reset flows, start API with `EZRULES_TESTING=false` and SMTP configured (for local stack: `EZRULES_SMTP_HOST=localhost`, `EZRULES_SMTP_PORT=1025`, `EZRULES_FROM_EMAIL=...`). `EZRULES_TESTING=true` skips SMTP sends and will break email-flow e2e tests.
10. Database-related functionality must be tested on the live test DB rather than mocked.
11. If functionality affects user experience/actions, update README and `docs/whatsnew.md`.
12. If you are asked to bump the version, bump the version first, then create or update the matching topmost version section in `docs/whatsnew.md` and place the current change notes under that new version heading. Do not add new changes under an older version section.
13. When tests are approved, run ALL tests, not selective subsets.
14. When the user requests the full test suite, also validate the demo Docker path by testing `docker compose -f docker-compose.demo.yml up --build` and confirming the demo stack starts successfully; tear it down afterward.
15. When tests require starting local services manually, run the API/backend and Angular frontend on random available high ports instead of standard ports like `8888` and `4200` to reduce the chance of blocking commonly used defaults.
16. When running the full test suite locally, always use private database names for this worktree/agent instead of shared names like `tests` or `ezrules`. This applies to backend pytest, CLI test helpers, reset-dev, and any Playwright/dev-stack runs.
17. Prefer the existing private E2E naming convention, for example `tests_e2e_<suffix>` and `ezrules_e2e_<suffix>`.
18. After tests are done, kill any API/backend and Angular dev servers you started manually, regardless of which ports were used.
19. After all tests pass, reset the dev environment using the same private dev DB you used for the run, not the shared `ezrules` DB.
20. Make sure that the new code does not affect the github action configurations. If it does, make sure the changes are reflectd in the testing infra in github actions

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
