# Documentation Map

This file is the quick reference for where documentation lives and what code is the source of truth.

## Primary Docs by Area
- `docs/index.md`: landing page and high-level product overview.
- `docs/getting-started/installation.md`: install and first-time setup.
- `docs/getting-started/quickstart.md`: UI-first local flow.
- `docs/getting-started/integration-quickstart.md`: API/service integration flow.
- `docs/getting-started/configuration.md`: env vars, runtime options, config matrix.
- `docs/api-reference/manager-api.md`: complete API v2 endpoint map.
- `docs/api-reference/evaluator-api.md`: `/api/v2/evaluate` contract and examples.
- `docs/user-guide/*.md`: operator workflows (analyst/admin/monitoring/rules/labels/lists).
- `docs/architecture/overview.md`: system boundaries and flows.
- `docs/architecture/deployment.md`: local deployment/runtime guide.
- `docs/troubleshooting.md`: symptom -> diagnosis -> fix.
- `docs/whatsnew.md`: release notes/changelog.
- `README.md`: repo-level setup and feature summary.

## Source-of-Truth Code by Area
- Backend app wiring: `ezrules/backend/api_v2/main.py`.
- Backend endpoint contracts: `ezrules/backend/api_v2/routes/*.py`.
- Backend request/response schemas: `ezrules/backend/api_v2/schemas/*.py`.
- Auth and permission behavior: `ezrules/backend/api_v2/auth/*.py`.
- Frontend routes/navigation: `ezrules/frontend/src/app/app.routes.ts`, `ezrules/frontend/src/app/components/sidebar.component.ts`.
- Frontend API usage: `ezrules/frontend/src/app/services/*.ts`.
- Frontend environment keys: `ezrules/frontend/src/environments/environment*.ts`.
- CLI/runtime commands: `ezrules/cli.py`.
- Runtime settings/env vars: `ezrules/settings.py`.

## Update Rules (Keep Docs in Sync)
1. If backend endpoints/methods/params/status codes/schemas/auth change:
   - Update `docs/api-reference/manager-api.md`.
   - Update `docs/api-reference/evaluator-api.md` if evaluate contract changed.
   - Update affected guides (`integration-quickstart`, `troubleshooting`, user guides).
2. If Angular routes, screen names, sidebar nav, or UI flows change:
   - Update `docs/getting-started/quickstart.md`.
   - Update relevant `docs/user-guide/*.md` pages.
3. If env vars, startup commands, ports, or deployment flow change:
   - Update `docs/getting-started/configuration.md`.
   - Update `docs/getting-started/installation.md`.
   - Update `docs/architecture/deployment.md`.
4. If behavior is user-visible:
   - Update `README.md`.
   - Update `docs/whatsnew.md`.

## Docs Validation Checklist
1. Build docs in strict mode:
   - `uv run mkdocs build --strict`
2. Ensure API map remains aligned with current OpenAPI (`app.openapi()` in `ezrules/backend/api_v2/main.py`).
3. Ensure documented UI paths match `ezrules/frontend/src/app/app.routes.ts`.

## Snippets
- Reusable snippets live in `docs/snippets/*.txt`.
- Keep include references aligned with snippet file names.
