# Plan: Implement Create Rule Page in Angular

## Summary
Add a "Create Rule" page to the Angular frontend, backed by a new `POST /api/rules` endpoint. The page has a two-column layout (rule details form on the left, test rule on the right), matching the existing rule-detail page style. After creation, navigate to the new rule's detail page.

---

## Files to Modify

### 1. `ezrules/backend/ezruleapp.py`
**Insert** a new `POST /api/rules` endpoint after line 289 (end of `api_update_rule`), before the existing `create_rule` Flask route (line 292).

- Decorator pattern: `@app.route("/api/rules", methods=["POST"])` + `@csrf.exempt` only (no auth — per task: "bypass security for now"), matching the existing PUT endpoint pattern.
- Accept JSON body: `rid`, `description`, `logic` — validate all three are non-empty strings.
- Compile via `RuleFactory.from_json({"rid": rid, "logic": logic, "description": description})` to validate syntax (same as PUT endpoint line 257).
- Create `RuleModel(rid=rid, logic=logic, description=description)` — do NOT set `o_id`; `fsrm.save_rule()` handles that for new rules (when `r_id is None`).
- Call `rule_engine_config_producer.save_config(fsrm)` after save.
- Return `{"success": True, "message": "Rule created successfully", "rule": {r_id, rid, description, logic, created_at, revisions: []}}`.
- Error responses: `{"success": False, "error": "..."}` with 400 status.

### 2. `ezrules/frontend/src/app/services/rule.service.ts`
- Add interfaces `CreateRuleRequest` (rid, description, logic) and `CreateRuleResponse` (success, message?, error?, rule?: RuleDetail) after the existing `UpdateRuleResponse` interface (line 66).
- Add method `createRule(data: CreateRuleRequest): Observable<CreateRuleResponse>` — POSTs to `this.apiUrl` (which is already `/api/rules`).

### 3. `ezrules/frontend/src/app/app.routes.ts`
- Import `RuleCreateComponent` from `./rule-create/rule-create.component`.
- Insert `{ path: 'rules/create', component: RuleCreateComponent }` **before** the `rules/:id` routes (route ordering matters — `create` would otherwise be captured as `:id`). Place it after `{ path: 'rules', ... }` and before `{ path: 'rules/:id/history', ... }`.

### 4. `ezrules/frontend/src/app/rule-list/rule-list.component.html`
- Line 23: Change `<a href="/create_rule"` to `<a routerLink="/rules/create"` (the "New Rule" header button).
- Line 84: Change `<a href="/create_rule"` to `<a routerLink="/rules/create"` (the empty-state "Create Rule" link).

---

## Files to Create

### 5. `ezrules/frontend/src/app/rule-create/rule-create.component.ts`
Standalone component, no `OnInit` (no data to load on mount). Imports: `Component`, `CommonModule`, `Router`, `RouterModule`, `FormsModule`, `RuleService`, `CreateRuleRequest`, `SidebarComponent`.

State: `rid`, `description`, `logic`, `testJson`, `testResult`, `testError`, `testing`, `saving`, `saveError` — all initialized at class level.

Methods:
- `handleTextareaTab(event)` — exact copy from rule-detail.component.ts (TAB inserts `\t` in textarea).
- `fillInExampleParams()` — calls `ruleService.verifyRule(this.logic)` and populates `this.testJson` with extracted params as JSON. Called via `(ngModelChange)` on the logic textarea.
- `testRule()` — calls `ruleService.testRule(this.logic, this.testJson)`, sets `testResult`/`testError`.
- `submitRule()` — constructs `CreateRuleRequest`, calls `ruleService.createRule()`. On success: navigates to `/rules/{response.rule.r_id}`. On error: sets `saveError` from response.
- `goBack()` — `router.navigate(['/rules'])`.

### 6. `ezrules/frontend/src/app/rule-create/rule-create.component.html`
Two-column layout identical to rule-detail. Structure:
- Sidebar + `ml-64` main content wrapper.
- Breadcrumb: `All Rules` (routerLink="/rules") > `Create Rule`.
- Left column "Rule Details" card:
  - Rule ID: `<input type="text" [(ngModel)]="rid">` (editable text input, placeholder "Enter rule ID").
  - Description: `<textarea [(ngModel)]="description">`.
  - Logic: `<textarea [(ngModel)]="logic" (keydown)="handleTextareaTab($event)" (ngModelChange)="fillInExampleParams()">` with `font-mono` class.
  - Save error banner (red, shown when `saveError` is set).
  - "Create Rule" button (green, disabled when `saving`, shows spinner when saving) + "Back to Rules" button (gray).
- Right column "Test Rule" card: exact same structure as in rule-detail.component.html (Test JSON textarea with tab support, Test Rule button, result/error display).

### 7. `ezrules/frontend/e2e/pages/rule-create.page.ts`
Page Object with locators: `heading`, `breadcrumb`, `ruleIdInput`, `descriptionTextarea`, `logicTextarea`, `submitButton`, `cancelButton`, `testJsonTextarea`, `testRuleButton`, `testResultSuccess`, `testResultError`, `saveErrorMessage`.

Methods: `goto()`, `fillRuleId(v)`, `fillDescription(v)`, `fillLogic(v)`, `fillTestJson(v)`, `clickSubmit()`, `clickCancel()`, `clickTestRule()`.

### 8. `ezrules/frontend/e2e/tests/rule-create.spec.ts`
Test groups:
- **Navigation**: "New Rule" button on list page navigates to `/rules/create`; Back button navigates to `/rules`; breadcrumb "All Rules" link navigates to `/rules`.
- **Form Fields**: All three fields (Rule ID, Description, Logic) are visible and fillable.
- **Test Rule Section**: Entering valid logic populates Test JSON via `/verify_rule`; clicking Test Rule with valid data shows success result.
- **Rule Creation**: Valid submission POSTs to `/api/rules`, receives 200, navigates to `/rules/<r_id>` detail page, and the detail page shows the created rule's rid. Use unique rid with `Date.now()` suffix.
- **Error Handling**: Invalid logic shows error and stays on create page; missing rid shows error.

### 9. `tests/test_create_rule_api.py`
Class `TestCreateRuleAPI`. Uses `session` and `logged_in_manager_client` fixtures. Inline imports of `RuleModel`/`Organisation` inside methods (matching existing test_web_endpoints.py pattern).

Tests:
- `test_api_create_rule_success` — POST valid data, assert 200, verify response shape, then GET `/api/rules/{r_id}` to confirm persistence.
- `test_api_create_rule_missing_rid` — empty rid → 400.
- `test_api_create_rule_missing_description` — empty description → 400.
- `test_api_create_rule_missing_logic` — empty logic → 400.
- `test_api_create_rule_no_body` — POST with no JSON → 400.
- `test_api_create_rule_invalid_logic` — invalid syntax → 400 with "Invalid rule logic" in error.
- `test_api_create_rule_persists_to_db` — POST, then `session.query(RuleModel).filter_by(rid=...)` confirms row exists.

---

## Verification Checklist

1. Restart manager: kill port 8888, run `uv run ezrules manager --port 8888`.
2. Backend tests: `EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests EZRULES_TESTING=true uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests` — zero `F`.
3. Code quality: `uv run poe check` — clean.
4. E2E tests: `cd ezrules/frontend && npm run test:e2e` — all pass (sequential, not parallel).

## Key Pitfalls
- Route order: `rules/create` must come before `rules/:id` in app.routes.ts.
- Do NOT set `o_id` on the new `RuleModel` — `fsrm.save_rule` sets it.
- `fillInExampleParams` will error silently on incomplete logic (expected — `/verify_rule` returns empty params).
- E2E creation tests use timestamp-unique rids to avoid collisions; no cleanup needed (matches existing pattern).
