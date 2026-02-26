# Parallel Playwright — Rebase Notes

Branch: `parallel-playwrith`
Rebase target: `main`

## What this branch does

Makes all Playwright E2E tests safe to run in parallel at the file level (`workers: 4`).

## Backend changes (`ezrules/backend/` and `ezrules/core/`)

### 1. `ezrules/backend/api_v2/auth/dependencies.py`
- Replaced `scoped_session` (thread-local) with a fresh `SessionLocal()` per request — the standard FastAPI pattern.
- Added `joinedload(User.roles)` in both `get_current_user` and `get_current_user_strict` to prevent lazy-load `DetachedInstanceError` under concurrent load.

### 2. `ezrules/core/rule_updater.py`
- Added `.with_for_update()` on the `save_config()` query to serialize concurrent writes to `rule_engine_config_history` (prevents `UniqueViolation` under parallel test load).

### 3. `ezrules/backend/api_v2/routes/rules.py`
- Added `DELETE /api/v2/rules/{rule_id}` endpoint (used by test cleanup in `afterEach`).

## Frontend changes (`ezrules/frontend/`)

### `playwright.config.ts`
- `workers` bumped from 2 → 4 (both CI and local).

### `e2e/tests/rule-detail.spec.ts` and `rule-edit.spec.ts`
- Refactored in previous session. Each test creates its own rule via `request.post()` in `beforeEach` and deletes it in `afterEach`.

### `e2e/tests/rule-revision.spec.ts`
- Full rewrite: removed dependency on "first rule in list"; now creates `E2E_REVISION_*` rule per test via API.

### `e2e/tests/rule-history.spec.ts`
- Same pattern; `E2E_HISTORY_*` prefix.

### `e2e/tests/backtesting.spec.ts`
- Same pattern; `E2E_BACKTEST_*` prefix.

### `e2e/tests/rule-create.spec.ts`
- Added `afterEach` cleanup: captures rule ID from URL after form submission, deletes via API.

## Known pre-existing failures (unrelated to this branch)

These fail even with `workers=1` in isolation — they require specific DB seed data:

- `e2e/tests/label-analytics.spec.ts` — 4 chart canvas tests require labeled events in the DB.
- `e2e/tests/backtesting.spec.ts:133` ("should expand result and show diff and outcome table") — requires a completed backtest with diff/outcome data in the DB.

## After rebase

1. Resolve any merge conflicts (likely in `routes/rules.py`, `dependencies.py`, `rule_updater.py`).
2. Restart the API: `uvicorn ezrules.backend.api_v2.app:app --port 8888 --reload` (or however it's started).
3. Run the full suite to verify: `cd ezrules/frontend && npx playwright test --workers=4 --reporter=line`
4. Expected: ~240 passed, 5 failed (the pre-existing ones above), 1 skipped.
