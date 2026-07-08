# Tooling
1. The project uses uv for environment and package management. Only use uv for Python-related package management. Never create virtual environments manually.
2. Code quality checks: `uv run poe check` (ruff format check, ty type check, ruff linting).
3. CLI smoke test: `uv run pytest -q tests/test_cli_smoke.py`.

# Verification Policy
Default to GitHub-hosted verification instead of local test execution.

- Always run `uv run poe check` locally before pushing a branch, opening a PR, or updating a PR. Fix any failures locally first so GitHub Actions does not get noisy code-quality/type/lint failures.
- Do not run local test suites, local Playwright runs, local backend suites, or local docs builds unless the user explicitly asks for local verification or the task is specifically about diagnosing a local-only bug.
- For normal feature/fix work, implement the change, run `uv run poe check`, create or update the PR, push it, and use GitHub Actions/PR checks as the verification source of truth for tests and full infra validation.
- Do not bring up local Postgres, Redis, Mailpit, API, Celery, Angular, or Docker demo stacks just to verify code before opening a PR. Use CI/CD infrastructure for that.
- If GitHub checks fail, inspect the failing CI logs, make a focused fix, push again, and let CI rerun.
- Local infra is still appropriate when the user explicitly asks to run the app for manual testing, requests a local demo recording, or reports a bug that only reproduces in their local topology.

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
uv run pytest -q --cov=ezrules.backend --cov=ezrules.core --cov-report=xml tests
```

## Notes
- `conftest.py` creates/drops the database named in `EZRULES_DB_ENDPOINT` and applies Alembic migrations (`upgrade head`) before tests.
- When running the full suite locally, always use a private DB name for the backend test run and a different private DB name for any dev/E2E stack. Never reuse shared names like `tests` or `ezrules`.
- If another Postgres container is bound to `5432` with different credentials, override `EZRULES_DB_ENDPOINT` accordingly.
- If uv cache permission errors occur in restricted environments, prefix with `UV_CACHE_DIR=/tmp/uv-cache`.
- CI parity sequence is: `uv sync --dev` -> `uv run alembic upgrade head` -> pytest command above.
- Prefer quiet test output by default: use backend pytest in quiet mode (`-q`) and keep coverage output in XML unless a failing run specifically needs the more verbose terminal report.
- Prefer the default quiet Playwright run (`npm run test:e2e`) instead of the verbose reporter variant. Use the verbose mode only when debugging failures interactively.

# Agentic Exploratory Testing
Agentic product exploration charters live under `tests/agentic_exploration/`. Treat them as free-testing prompts for finding unknown product issues, not deterministic CI gates.

When asked to run agentic exploration:
- Use `tests/agentic_exploration/RUN_CONTRACT.md` plus exactly one charter from `tests/agentic_exploration/charters/` per agent.
- Run against a private local/dev database and disposable test data only. Never use shared `tests` or `ezrules` databases.
- Ask agents to report findings using `tests/agentic_exploration/REPORT_TEMPLATE.md`.
- Do not let exploration agents modify source code or fix bugs during the exploration run; they should report evidence and deterministic-test recommendations.
- Convert credible repeatable findings into backend business tests or Playwright E2E tests before relying on them as release gates.
- Generated exploration reports belong under `tests/agentic_exploration/reports/` or `artifacts/` and should not be committed unless explicitly requested.

# Local Agent Stack Topology
When bringing up API + Angular for manual testing, Playwright, or agentic exploration, use the correlated stack scripts instead of hand-picking ports:

```bash
docker compose up -d postgres redis mailpit   # if not already running
./scripts/start-agent-stack.sh && source .env.agent-stack && ./scripts/verify-stack.sh
./scripts/stop-agent-stack.sh                   # when finished
```

**Run start, source, and verify in one chained command** (or the same shell turn). If a later agent turn finds connection refused, rerun `./scripts/start-agent-stack.sh --no-reset --suffix <same-suffix>` before verifying again.

`--no-reset` is only for reusing the **same** `--suffix` whose database was already initialized by a prior `./scripts/start-agent-stack.sh` (or `reset-dev`) in this worktree. A **new suffix always needs a full start** without `--no-reset`.

`start-agent-stack.sh` writes `.env.agent-stack` with matching values for:
- API listen port (`--port`)
- frontend dev-server port
- `EZRULES_FRONTEND_API_URL` (frontend → API)
- `EZRULES_CORS_ALLOWED_ORIGINS` and `EZRULES_APP_BASE_URL` (API → browser)
- private DB name `ezrules_e2e_<suffix>`
- Playwright overrides `E2E_BASE_URL` / `E2E_API_BASE_URL`

Before claiming login works:
1. Run `./scripts/verify-stack.sh` (topology + login smoke test by default)
2. Or curl login directly after `source .env.agent-stack`:

```bash
curl -fsS -X POST "${API_URL}/api/v2/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=${AGENT_STACK_ADMIN_EMAIL}" \
  --data-urlencode "password=${AGENT_STACK_ADMIN_PASSWORD}"
```

The login endpoint expects OAuth2 **form fields** `username` and `password`, not JSON `email`/`password`.

For browser confirmation, open `${FRONTEND_URL}/login` and check DevTools → Network: the login POST must target `${API_URL}` and must not be blocked by CORS.

If you must start services manually, override **all four** together: API port, frontend port, `EZRULES_FRONTEND_API_URL`, and `EZRULES_CORS_ALLOWED_ORIGINS`. See `settings.agent-stack.env.example`.

# Common Development Commands
- **Install dependencies**: `uv sync`
- **Initialize database**: `uv run ezrules init-db`
- **Add user**: `uv run ezrules add-user --user-email admin@example.com --password admin`
- **Start disposable agent stack** (API + frontend + private DB): `./scripts/start-agent-stack.sh`
- **Start API service** (FastAPI, includes evaluator): `uv run ezrules api --port 8888`
- **Start Celery worker** (required for backtesting): `uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo`
- **Generate test data**: `uv run ezrules generate-random-data --n-rules 10 --n-events 100`

# Git and Pull Requests
1. Never add `codex`, `[codex]`, or similar agent/tool branding to pull request titles.
2. Never push branches or commits unless the user explicitly asks for a push, publish, PR creation/update, or another action that clearly requires pushing.

# VS Code Launch Configs (.vscode/launch.json)
When creating a new git worktree for this repository, copy the root `.vscode/` folder into the new worktree before starting work so all launch/run configurations remain available there.
When working in a new git worktree, proactively ensure dependencies are installed in that worktree before starting: run `uv sync` for Python deps and make sure frontend deps are present in `ezrules/frontend/` (run `npm install` there if `node_modules` is missing) so the user does not have to do manual dependency setup.

For bugs reported against a running local app, launch config, browser auth flow, or frontend/backend connectivity, reproduce the exact local topology first before drawing conclusions:
- Start from the active `.vscode/launch.json`, `settings.env`, currently used ports, and the user's actual local workflow unless the user says otherwise.
- Verify the full browser path, not just direct API behavior: confirm the request URL the browser is using, whether it reaches backend logs, the effective frontend runtime config / served bundle API base URL, and the backend CORS response for the real frontend origin.
- Treat direct API calls, unit tests, and alternate E2E harnesses as secondary evidence only; they do not close a local-setup bug unless they exercise the same topology the user is running.
- For local frontend/backend connectivity bugs, do not conclude until you have checked all of: effective frontend API base URL, backend listener state, browser-origin request behavior, and launch-config env vars that affect routing or CORS.

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
2. Before pushing or reporting task completion, ensure `uv run poe check` passes locally, then create or update the PR and confirm the relevant GitHub Actions checks have passed unless the user explicitly requested local-only work.
3. Any new imports must go to the top of the file (no inline imports in functions).
4. Any new functionality must be covered with tests.
5. When implementing new functionality, explicitly ask the user whether permissions and audit logging should be included in scope.
6. Do not silently choose a short-term convenience implementation when a cleaner long-term design exists, including cases where the long-term design needs migrations, schema changes, or broader plumbing. Surface the tradeoff explicitly, recommend the durable approach, and let the user decide scope before implementing the shortcut.
7. **FOR ANGULAR FRONTEND CHANGES**: Any new pages/navigation must have Playwright e2e tests in `ezrules/frontend/e2e/tests/` plus corresponding page objects in `e2e/pages/*.page.ts`. New or modified Playwright coverage must follow the repeated targeted verification rules below.
8. **FOR USER-VISIBLE UI FEATURES OR WORKFLOWS**: When explicitly recording a browser demonstration, use a pre-authenticated browser/session and skip the login page entirely. Use human-readable demo data and UI names that look realistic, for example "High Value Sender Volume" or "Premium Customer Review", never throwaway names such as `test_shit_23`, `foo`, `asdf`, or random-looking identifiers. Record against a live local stack only when a demo is requested or clearly required. Use a private dev DB, run the backend/frontend on random high ports, save the recording artifact under `artifacts/` in the worktree, and keep the proof focused on the implemented behavior. Pace demo recordings for human viewing and social sharing: move slowly, pause 1-2 seconds before and after each meaningful click/type/navigation, keep key UI states visible long enough to understand, and avoid ultra-short recordings where the workflow cannot be followed.
9. **FOR NEW OR UPDATED FUNCTIONALITY**: Check whether `README.md`, docs pages, and `docs/assets/readme/` screenshots or GIF demos need to be updated. If the change affects a captured UI surface or a documented workflow, regenerate the relevant asset from a live local stack and zoom into the specific UI area that proves the behavior; if not, mention in the final report that screenshots/GIFs were reviewed and did not need changes.
10. When the browser recording is generated as `.webm`, convert it to a shareable `.mp4` using H.264 + `yuv420p` + `faststart` so it can be uploaded to services such as X/Twitter. Preferred command: `ffmpeg -y -i input.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 128k output.mp4`. File must be named accorind to the feature it demos.
11. If a new endpoint is implemented, restart the API server if needed.
12. If one e2e test fails, stop and fix the root cause before waiting for all failures.
13. For Playwright runs that include invite/reset flows, start API with `EZRULES_TESTING=false` and SMTP configured (for local stack: `EZRULES_SMTP_HOST=localhost`, `EZRULES_SMTP_PORT=1025`, `EZRULES_FROM_EMAIL=...`). `EZRULES_TESTING=true` skips SMTP sends and will break email-flow e2e tests.
14. Database-related functionality must be tested on the live test DB rather than mocked.
15. If a task changes shipped code, API behavior, or user-visible behavior, bump the project version as part of the same change. Choose a **patch** bump by default. Choose a **minor** bump when the change introduces a new feature, new user-visible workflow, or new API surface that should read as a feature release.
16. The version bump must happen **before** editing `docs/whatsnew.md`. Treat `pyproject.toml` as the canonical project version source unless the repo introduces a deeper override later. After bumping the version, create or update the matching topmost version section in `docs/whatsnew.md` and place the current change notes there. Never add new work under an already released older version section, and never update `docs/whatsnew.md` before the version bump is in place.
17. Only bump the version **once per unreleased feature/release line**. After a branch or task has already introduced a new unreleased version section in `docs/whatsnew.md`, any follow-up fixes, polish, review feedback, or minor corrections for that same feature line must stay under that already-bumped version instead of creating another new version. Bump again only when starting a genuinely new release-worthy change beyond the current unreleased scope.
18. Verification should be scoped by blast radius. Do not default to the full Playwright suite for every frontend change.
19. For any backend, CLI, data-model, or API-contract change, run the full backend/local verification relevant to shipped behavior. This normally includes backend pytest, CLI helper coverage when affected, docs/build checks when affected, and any supporting verification documented here.
20. For any new or modified Playwright spec, run the affected spec file(s) with `--project=chromium --workers=1 --repeat-each=5`.
21. If the frontend change touches shared page objects, route guards, auth/session state, runtime settings, ordering/reordering flows, hover/highlight behavior, polling/refresh behavior, tested-events flows, dashboard/rule analytics flows, or another stateful/shared UI surface, increase the targeted Playwright run to `--repeat-each=10`.
22. After the repeated targeted Playwright run passes, rerun the same targeted command once more without resetting the private dev DB. This is required to catch cleanup leaks and state-coupling between runs.
23. If a frontend change touches global routing, app shell/sidebar/navigation, runtime config, shared services used across multiple pages, or otherwise has clearly app-wide impact, expand verification to the affected spec cluster. Run the full Playwright suite only when the change is clearly cross-app, when repeated targeted runs still suggest broader coupling, or when the user explicitly asks for the full suite.
24. When the user requests the full test suite, run the full local suite and also validate the demo Docker path by testing `docker compose -f docker-compose.demo.yml up --build` and confirming the demo stack starts successfully; tear it down afterward.
25. When tests require starting local services manually, prefer `./scripts/start-agent-stack.sh` so API port, frontend port, runtime API URL, and CORS origins stay aligned. If you cannot use the script, pick random available high ports instead of `8888`/`4200` and override all correlated env vars together (see **Local Agent Stack Topology** above).
26. Always use private database names for this worktree/agent instead of shared names like `tests` or `ezrules`. This applies to backend pytest, CLI test helpers, reset-dev, and any Playwright/dev-stack runs. Prefer the existing private E2E naming convention, for example `tests_e2e_<suffix>` and `ezrules_e2e_<suffix>`.
27. After tests are done, kill any API/backend and Angular dev servers you started manually, regardless of which ports were used.
28. After verification completes, reset the private dev environment using the same private dev DB you used for the run, not the shared `ezrules` DB.
29. Make sure that the new code does not affect the github action configurations. If it does, make sure the changes are reflectd in the testing infra in github actions

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
7. For user-facing changes, update README and then update `docs/whatsnew.md` only after the version bump described above. Do not record new change notes under the current released version unless the task explicitly says to amend that release.
8. Snippet includes live in `docs/snippets/*.txt`; keep include paths aligned
9. Be factual; only write sections that can be backed by code
