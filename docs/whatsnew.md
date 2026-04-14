# What's New

## v1.10.0

* **Documented ECS/Fargate deployment example**: The deployment guide now documents one AWS-oriented topology for `frontend`, `api`, `celery-worker`, `celery-beat`, and the one-shot init/migration task, plus the required Postgres and Redis dependencies.
* **Production frontend no longer falls back to localhost**: Angular production builds now default to same-origin API calls, while local single-host validation stacks opt into `http://localhost:8888` explicitly at image build time.
* **Configurable production CORS**: Backend CORS is no longer hard-coded to localhost-only behavior; deployments can now keep the recommended same-origin ALB routing or explicitly allow named browser origins / regexes through environment configuration.
* **Compose stacks now include Celery beat**: Demo, local production-validation, and development Docker stacks now ship the required scheduler process so async field-observation and shadow drains match the documented runtime topology.
* **Legacy deployment manifests removed**: The obsolete `deployment/aws` and `deployment/k8s` manifests were deleted because they no longer reflect the current unified FastAPI + Celery + Postgres + Redis architecture.
* **Local dev login path restored**: Angular local development now imports the dev environment again, and the VS Code FastAPI launch config explicitly allows `http://localhost:4200`, so login requests reach `http://localhost:8888` instead of falling back to broken same-origin `/api` calls on the dev server.

## v1.9.0

* **Ordered main-rule execution**: Main rules now carry an explicit `execution_order`, and organisations can switch main-lane evaluation between legacy `all_matches` behavior and a new `first_match` mode that persists only the earliest matching main rule.
* **Settings control for main-lane semantics**: **Settings → General** now exposes `main_rule_execution_mode`, so operators can enable first-match serving without changing allowlist behavior.
* **Rule ordering controls and audit trail**: The Rules list now shows execution order only when first-match mode is enabled, supports button-based reordering with a dedicated `reorder_rules` permission, and records reorder actions in rule history.

## v1.8.0

* **Paused rule lifecycle state**: Rules can now be moved from `active` to `paused` without archiving or editing their logic, which removes them from live production evaluation while preserving the rule row, history, and later resume path.
* **Resume workflow and audit trail**: Added explicit resume behavior for paused rules, with lifecycle audit entries now recording `active -> paused` and `paused -> active` transitions.
* **Dedicated pause permission**: Pausing active rules now requires a new `pause_rules` permission, separate from both generic rule editing and live promotion.

## v1.7.1

* **Async shadow evaluation**: Live `/api/v2/evaluate` calls now enqueue shadow comparisons after the canonical event write and let a periodic Celery drain persist shadow results later, so shadow-enabled traffic no longer waits for best-effort shadow rule execution before the production response returns.

## v1.7.0

* **Uploaded labels in Tested Events**: The Tested Events table now shows the uploaded label applied to each stored event, so analysts can scan CSV-labeled traffic without opening analytics or raw database records.

## v1.4.1

* **Neutral outcome setting**: Settings now lets each organisation designate one existing outcome as the reusable `neutral_outcome`. Allowlist rule validation now depends on that selected neutral outcome instead of an implicit allowlist-only default.
* **Visible allowlist guidance**: The rule create/edit flows now show the current neutral outcome explicitly in their allowlist helper text, so authors can immediately see which value allowlist rules must return.
* **Invalid allowlist rule warnings**: Settings now revalidates existing allowlist rules against the selected neutral outcome and flags any rules that no longer comply.
* **Neutral outcome permissions and audit trail**: Updating `neutral_outcome` now requires a dedicated `manage_neutral_outcome` permission, and each change is recorded in outcome audit history as `neutral_outcome_updated`.

## v1.4.0

* **Async field observation persistence**: Live `/api/v2/evaluate` calls now push field observations into Redis and let a periodic Celery drain batch them into Postgres, removing non-canonical observation writes from the critical response path. Observation listings are now eventually consistent for live traffic, while the **Test Rule** panel still records observations immediately.
* **Allowlist rule lane**: Rules can now be marked as `allowlist` in the create/edit UI and API. When any active allowlist rule matches, ezrules short-circuits the main rule set and returns the configured neutral outcome immediately.
* **Allowlist visibility in the UI**: Rule list and detail views now display an `ALLOWLIST` / `Allowlist` badge so these rules are visually distinct from the main rule set.
* **Allowlist guardrails**: Allowlist rules must return the configured neutral outcome (default `RELEASE`), and they cannot be deployed to shadow or rollout flows.

## v1.3.1

* **Configurable active-rule auto-promotion**: Organisations can now enable `auto_promote_active_rule_updates` under **Settings → General** so edits to already active rules stay live immediately instead of always falling back to a draft.
* **Permission boundary preserved for live edits**: Even with active-rule auto-promotion enabled, saving an active rule in place still requires `PROMOTE_RULES` in addition to `MODIFY_RULE`, so draft editing and live deployment remain separate capabilities.

## 1.3.0

* **CodeMirror rule editor**: The rule create/edit flows now use a proper syntax-highlighted editor instead of a plain textarea, with line numbers, Python-aware highlighting, and dedicated styling for ezrules `$field` and `@userList` notation.
* **Structured rule diagnostics**: `POST /api/v2/rules/verify` now returns explicit validation metadata (`valid`, `errors`, and referenced user lists), and the Angular UI surfaces syntax and missing-list issues inline with line/column context while you type.
* **Rule authoring hints**: The editor now offers autocomplete for observed fields and known user lists, plus live detected-reference chips so rule writers can see which `$fields` and `@lists` the current source resolves to before testing or saving.

## v1.2.6

* **Persistent backtest jobs and controls**: Backtest history rows now persist queue status, completion timestamps, and full result metrics, and the Rule Detail page can cancel queued/running jobs and retry failed jobs without losing the original snapshot.
## v1.2.5

* **Dashboard rule-activity rankings**: The Dashboard now shows ranked **Most Firing Rules** and **Least Firing Rules** for the selected time window, uses stored non-null rule outcomes only, includes active zero-hit rules in the least-firing list, and links each ranked row straight to the matching rule detail page.

## v1.2.4

* **Explicit organisation bootstrap CLI**: `uv run ezrules init-db` now initializes the schema and global action catalogue without auto-creating a default tenant, and the new `uv run ezrules bootstrap-org --name ... --admin-email ... --admin-password ...` command creates an organisation, seeds default roles/user lists, and ensures the first admin user exists.
* **Org-aware CLI targeting**: `add-user`, `generate-random-data`, and `export-test-csv` now accept `--org-name`, and fall back to implicit selection only when exactly one organisation exists.
* **Reset-dev now bootstraps a named dev org**: `uv run ezrules reset-dev` now creates an explicit development organisation before seeding demo data, rather than relying on the legacy implicit `base` organisation.

## v1.1.2

* **Removed implicit runtime label/outcome bootstrap**: `init-db` and the database-backed label/outcome managers no longer auto-create default outcomes or labels during normal application flows. `reset-dev` still seeds the demo catalogs and curated outcome→label pairs for local demo/test environments.

## v1.2.1

* **Permission-aware navigation and route access**: The Angular app now hides sidebar entries for pages the current user cannot access and redirects direct deep links to an explicit access-denied page instead of letting the user discover the problem through a later `403`.
* **Read-only management states**: Rules, users, roles, labels, outcomes, user lists, field types, settings, shadow rules, and rollout views now hide mutating controls when the matching create/modify/delete permission is missing, while still allowing permitted read access.

## v1.1.0


* **Rule rollouts with stable traffic bucketing**: Active rules can now serve a candidate version to a configurable percentage of live traffic, compare candidate vs control on the same evaluated events, and promote or remove the rollout from a dedicated **Rule Rollouts** page.
* **Org-aware manager JWTs**: Access tokens now include the authenticated user's organisation, and the API rejects access tokens whose org claim no longer matches the stored user membership.
* **Core admin CRUD is org-scoped**: Users, outcomes, user lists, and field type configs/observations now resolve organisation context from auth instead of fixed org constants.
* **Roles and labels are org-owned**: `Role` and `Label` now belong to an organisation, the same role/label name can exist in different orgs, and user-role assignment rejects cross-org roles.
* **Label usage is org-scoped**: Label CRUD, assignment, CSV uploads, rule-quality label options, and label analytics now operate only on the caller's organisation.
* **Audit trail org completion**: Label, user-account, and role-permission history now carry `o_id`, and the related audit summary/count endpoints only return the caller's organisation.
* **Backtesting/bootstrap stop assuming org 1**: Backtest workers derive org context from the selected rule/request, and `init-db`, `init-permissions`, `add-user`, `generate-random-data`, and `reset-dev` now seed roles, labels, and rule-quality defaults in the provisioned organisation instead of a fixed global org.
* **Fresh-init user ownership**: `User.o_id` is now mandatory, and fresh database/bootstrap flows create an organisation before creating users so clean rebuilds work with org-aware auth.
* **DB-level tenant integrity hardening**: PostgreSQL now rejects cross-org user-role links and cross-org event-label links even if someone bypasses the API, and `EZRULES_ORG_ID` is no longer a documented runtime tenant selector.
* **Frontend runtime-config hardening**: Frontend builds now regenerate `runtime-config.js` instead of baking in stale checked-in API URLs, so the demo stack and production image no longer inherit old local dev ports.
* **Rules page evaluate UX cleanup**: The Rules header no longer renders a dead browser link to the evaluator service, and the How to Run panel now shows the runtime manager API `/api/v2/evaluate` endpoint instead of a stale `localhost:9999` example.
* **Backtest status refresh fix**: Rule Detail now loads task status for every backtest result card on page load, so completed backtests no longer stay stuck at `In Progress` until you expand them.
* **Required field contracts**: Field type settings now support a `required` flag. Live `/api/v2/evaluate` requests reject events with missing or `null` values for required fields before any rule runs or storage occurs.
* **Strict lookup error clarity**: When a rule references a non-required field that is absent from an event, live evaluation now returns a clear `400` lookup error instead of a generic internal failure, and the **Test Rule** panel shows the same reason inline.
* **Rule verify warnings**: `POST /api/v2/rules/verify` now returns advisory warnings for referenced fields that have never been observed in traffic or rule-test payloads, and the Angular create/detail editors surface those warnings while you edit.
* **Backtest eligibility reporting**: Backtests now apply the same field normalization rules as live evaluation, compare stored vs proposed logic on a shared eligible subset, and report `eligible_records`, `skipped_records`, and explanatory warnings when older traffic is excluded.

## v0.24.3

* **Label-aware backtesting**: Backtest task results on the Rule Detail page now include historical label counts plus stored/proposed precision, recall, and F1 by outcome→label pair when labeled events exist in the backtest window.
* **Labels CSV upload in Angular UI**: The Labels page now includes a dedicated CSV upload panel with row-level success/error feedback, so batch labeling no longer depends on the retired Flask templates.
* **Assignment audit trail for labels**: Manual labeling and CSV uploads now record label-history entries with event details, and label assignment lookups are scoped to the active organization instead of the first matching `event_id`.
* **Reset-dev CSV seed file**: `uv run ezrules reset-dev` now writes a root-level `test_labels.csv` from the generated labeled events, so every fresh dev reset leaves behind a ready-to-upload Labels CSV.


## v0.24.1

* **Inline Tested Events payload highlighting**: The Tested Events detail view now keeps the payload in a single JSON block and highlights referenced top-level fields inline, instead of expanding the payload into a long field-by-field list.
* **Rule-focused hover behavior**: When no rule is hovered, the payload shows the union of fields referenced by all triggered rules. Hovering a specific triggered rule narrows the highlight to just the fields used by that rule.
* **Compose bootstrap fixes**: The backend Docker image now includes Alembic config and migration files, `docker-compose.demo.yml` now recreates the demo database on each run to avoid stale-volume failures, and `docker-compose.prod.yml` upgrades persisted databases before startup.

## v0.24.0

* **Dedicated rule-promotion permission**: Added `PROMOTE_RULES` so draft promotion and shadow-to-production promotion are separated from general rule editing. `MODIFY_RULE` still covers editing and shadow deploy/remove, while `PROMOTE_RULES` is now required for both promotion paths.
* **Permission-aware promotion controls**: The Angular UI now hides draft and shadow promotion buttons for users whose effective permissions do not include `PROMOTE_RULES`.
* **Current-user permissions in API**: `GET /api/v2/auth/me` now includes the authenticated user's effective permission names so the frontend can hide or show role-gated actions without reimplementing permission resolution client-side.

## v0.23.0

* **Tested Events view**: Added a dedicated **Tested Events** page in the Angular UI so analysts can inspect the latest stored transactions, see the resolved outcome, expand the raw event payload, review every triggered rule per event, jump directly from triggered rules to the matching rule detail page, and refresh the list without reloading the browser.
* **Tested Events API**: Added `GET /api/v2/tested-events` for retrieving recent stored evaluations with event payloads, outcome counters, and triggered rule metadata.
* **Rule field highlighting in Tested Events**: Triggered rules now expose the top-level event fields they reference. The Tested Events detail panel highlights the union of referenced fields by default and narrows the highlight to a single rule while you hover that rule.

## v0.20.0

* **Settings-aware rule test JSON**: The rule create/detail test panels now prefill sample JSON with demo-friendly values that respect stored field-type metadata and observed types, so live demos no longer start from empty strings.
* **Demo-ready rule-quality defaults**: `uv run ezrules reset-dev` now activates a curated demo pair set (`RELEASE -> CHARGEBACK`, `HOLD -> CHARGEBACK`, `CANCEL -> FRAUD`) so Rule Quality reports have meaningful scored pairs immediately after a reset.
* **Rule-quality ranking cleanup**: Best/Worst rule summaries now exclude unscored rules whose curated pairs never fired, avoiding misleading `N/A` rankings in generated reports.
* **Bombardment/demo schema alignment**: `scripts/bombard_evaluator.py` now emits the richer demo-event payloads used by the seeded rule pack, so bombardment traffic produces real rule outcomes instead of mostly no-op evaluations.
* **Rule rollback workflow**: Rule history now supports rolling back to a selected historical revision without deleting any prior versions. Rollback copies the chosen revision's logic and description into a new draft version, so the previous live version remains in the audit trail.
* **Rollback API and UI**: Added `POST /api/v2/rules/{id}/rollback` plus rollback actions in the Rule History timeline with a confirmation dialog that previews the current-to-target diff before creating the new draft version.

## v0.20

* **Rule Quality curated pairs**: Rule Quality reports now compute only analyst-configured curated outcome→label pairs (instead of all observed pairs), while preserving existing precision/recall/F1 and best/worst rule summaries.
* **Curated pair catalog in Settings**: Added centralized pair management under **Settings → General** with create/toggle/delete controls and outcome/label dropdowns.
* **New settings APIs for curated pairs**: Added CRUD endpoints under `/api/v2/settings/rule-quality-pairs` plus `/options` for dropdown catalogs.
* **Async report snapshots**: Added `POST/GET /api/v2/analytics/rule-quality/reports` to request and poll persisted snapshots. Reports are frozen at a specific `freeze_at` timestamp and are reused until an explicit refresh request (`force_refresh=true`) is made.
* **Pair-set-aware report cache**: Rule quality report reuse now includes a pair-set hash, so changing curated pairs invalidates stale cached reports automatically.
* **Runtime lookback controls**: `GET /api/v2/analytics/rule-quality` now supports `lookback_days`. A new **Settings → General** page persists the default lookback via `GET/PUT /api/v2/settings/runtime` so teams can bound query windows without redeploying.
* **Bombardment fraud labeling**: Enhanced `scripts/bombard_evaluator.py` to optionally mark a small random portion of successful evaluations as fraud labels (default 1%) using `--fraud-rate` and labels API calls.
* **Fraud-shaped demo data generation**: `uv run ezrules generate-random-data` now seeds correlated payment events and list-backed rules that look more like analyst-facing fraud operations, including CNP geo mismatch, card-testing bursts, account-takeover reset patterns, and payout cash-out scenarios.
* **Showcase rule patterns in demo seed**: The generated sample rule set now also includes a few intentionally illustrative rules that demonstrate nested branching, loop-based signal counting, and customer-baseline computations.
* **Observation write-path optimization**: Field observations are now upserted in one query per event instead of one lookup per field, which matters much more now that demo events carry richer payloads.

## v0.18

* **Rule lifecycle states**: Rules now carry lifecycle metadata with `status` (`draft`, `active`, `archived`), `effective_from`, `approved_by`, and `approved_at`.
* **Promotion workflow**: Added `POST /api/v2/rules/{id}/promote` to transition draft rules to active with approver audit attribution.
* **Archive workflow**: Added `POST /api/v2/rules/{id}/archive` to archive rules and remove active rules from production evaluation.
* **Delete endpoint documented and permissioned**: `DELETE /api/v2/rules/{id}` is explicitly documented and guarded by `DELETE_RULE`.
* **UI lifecycle controls**: Rule list now shows lifecycle badges and includes promote/archive actions.
* **Audit trail enrichment**: Rule history entries now persist lifecycle/approval metadata plus explicit rule actions (`promoted`, `deactivated`, `deleted`) with target status transitions; deleted rules retain audit history and remain queryable via `GET /api/v2/audit/rules/{rule_id}`.
* **E2E setup guardrail**: Frontend e2e docs now explicitly require starting API with `EZRULES_TESTING=false` for invite/reset email flows; testing mode disables SMTP delivery and causes those tests to fail.

## v0.17

* **Invitation onboarding flow**: Added `POST /api/v2/users/invite` for admin-triggered email invitations. Invited users can complete onboarding via `POST /api/v2/auth/accept-invite` and set their own password.
* **Self-service password reset**: Added `POST /api/v2/auth/forgot-password` and `POST /api/v2/auth/reset-password` with one-time, expiring reset tokens. Admin intervention is no longer required for standard password resets.
* **Email delivery settings**: Added SMTP configuration keys (`EZRULES_SMTP_HOST`, `EZRULES_SMTP_PORT`, `EZRULES_SMTP_USER`, `EZRULES_SMTP_PASSWORD`, `EZRULES_FROM_EMAIL`) and `EZRULES_APP_BASE_URL` for invite/reset link generation.
* **Frontend auth pages**: Added dedicated pages/routes for invite acceptance, forgot password, and reset password. Login now includes a "Forgot password?" path.
* **Security hardening**: Invitation and reset tokens are stored as SHA-256 hashes, checked for expiration, and enforced as single-use. Successful password reset revokes active refresh sessions.

## v0.16

* **Full-stack Docker Compose**: Two new compose files replace the previous infrastructure-only setup.
  * `docker-compose.demo.yml` — starts the complete stack (PostgreSQL, Redis, Celery worker, FastAPI API, Angular frontend) and seeds the database with 10 sample rules and 100 events. One command to a working UI: `docker compose -f docker-compose.demo.yml up --build`.
  * `docker-compose.prod.yml` — same full stack with an empty database. Credentials are read from a `.env` file (template provided as `.env.example`).
* **`Dockerfile.frontend`**: New multi-stage Dockerfile (Node 20 build → nginx serve) for the Angular frontend.
* The original `docker-compose.yml` (PostgreSQL + Redis only) is unchanged and remains the recommended setup for local development.
* **Outcome resolution hierarchy**: Settings now includes an **Outcome Resolution** section where admins can order allowed outcomes by severity. When multiple rules return different outcomes for the same event, ezrules now computes and persists a single `resolved_outcome` based on that hierarchy while still keeping the per-outcome counts.
* **API key authentication on evaluate**: `POST /api/v2/evaluate` now requires credentials. Pass an `X-API-Key` header with a key created via `POST /api/v2/api-keys`, or a standard Bearer JWT. Unauthenticated requests receive `401 Authentication required`.
* **API key management**: New endpoints `POST /api/v2/api-keys`, `GET /api/v2/api-keys`, `DELETE /api/v2/api-keys/{gid}` allow administrators with the `MANAGE_API_KEYS` permission to create, list, and revoke service API keys. The raw key is returned exactly once at creation and is never stored in plain text (only a SHA-256 hash is retained).
* **Body size limit**: All API requests are now rejected with `413 Request body too large` when the `Content-Length` header exceeds 1 MB (configurable via `EZRULES_MAX_BODY_SIZE_KB`).
* **Error sanitisation**: Internal errors from evaluate no longer leak exception messages; the response body is always `{"detail": "Evaluation failed"}`.

## v0.15

* **Server-side session revocation**: Refresh tokens are now tracked in a `user_session` database table. Logging out invalidates the refresh token immediately, preventing reuse even if a token is intercepted after logout.
* **Refresh token rotation**: Each call to `POST /api/v2/auth/refresh` deletes the presented token and issues a new one. A refresh token can be used exactly once; reuse returns `401 Session not found or already revoked`.
* **Logout endpoint**: New `POST /api/v2/auth/logout` endpoint accepts the current refresh token (plus a valid access token in the `Authorization` header) and deletes the session server-side. Multiple concurrent sessions (e.g. multiple browsers) are supported — only the presented token is revoked.
* **Lazy session cleanup**: Expired session rows for a user are deleted automatically on login, refresh, and logout, keeping the `user_session` table small without a background scheduler.

## v0.14

* **Shadow Rule Deployment**: Rules can now be deployed to a "shadow" environment that evaluates them against every incoming live event without affecting production outcomes. Shadow results are stored in a dedicated `shadow_results_log` table and never returned to callers. This complements backtesting (historical) with continuous live validation.
* **Deploy to Shadow button**: In the Rule Detail edit panel, a new amber "Deploy to Shadow" button sends the current draft of the rule logic to the shadow config.
* **Shadow Rules page**: A new **Shadow Rules** page (accessible from the sidebar) lists all rules currently in shadow, shows a summary of recent shadow outcomes, and provides per-rule "Promote to Production" and "Remove" actions.
* **Promote to production**: Promoting a rule moves its logic from the shadow config into the production config in one atomic step, then clears it from shadow. Both the production and shadow rule executors are invalidated so they pick up the change on the next request.
* **SHADOW badge**: Rules that have an active shadow version are annotated with an amber `SHADOW` badge in the Rule List and a "Shadow version active" badge in Rule Detail view mode.
* **New API endpoints**: `POST /api/v2/rules/{id}/shadow`, `DELETE /api/v2/rules/{id}/shadow`, `POST /api/v2/rules/{id}/shadow/promote`, `GET /api/v2/shadow`, `GET /api/v2/shadow/results`.
* **`in_shadow` field**: The `GET /api/v2/rules` response now includes `in_shadow: bool` on each rule item.

## v0.13.1

* **New PR Playwright E2E workflow**: added a dedicated GitHub Actions workflow that runs single-threaded Playwright end-to-end tests for pull requests against `main`, including backend/frontend startup and report artifact upload.

## v0.12

* **Field type management**: ezrules now auto-discovers the JSON types of event fields by observing traffic through `/api/v2/evaluate` and the **Test Rule** panel. Operators can declare a canonical type for each field (`integer`, `float`, `string`, `boolean`, `datetime`, `compare_as_is`) under **Settings → Field Types**. Values are cast to the declared type before rule execution, so comparisons like `$amount > 500` behave correctly regardless of how values arrive in JSON.
* **Per-type observation tracking**: field observations are recorded per `(field_name, observed_type)` pair, so if `amount` has been seen as both `int` and `str` you will see two separate rows with individual occurrence counts. This helps identify data quality issues upstream.
* **Casting at evaluation and test time**: `/api/v2/evaluate` rejects requests with a `400` error when a value cannot be cast to the configured type. The **Test Rule** panel surfaces the same error inline, giving immediate feedback before deployment.
* **Field type audit trail**: every create, update, and delete of a field type configuration is recorded in the audit trail. Accessible via **Audit Trail → Field Type History** in the UI or `GET /api/v2/audit/field-types`.
* **New API endpoints**: `GET /api/v2/field-types`, `GET /api/v2/field-types/observations`, `POST /api/v2/field-types`, `PUT /api/v2/field-types/{field_name}`, `DELETE /api/v2/field-types/{field_name}`, `GET /api/v2/audit/field-types`.
* **Sidebar Settings section**: the sidebar now groups **Role Management** and **Field Types** under a collapsible **Settings** section header.

## v0.11.2

* **License metadata consolidated**: License declarations in project metadata and documentation are now aligned with the repository's `LICENSE` file. ezrules is documented and published under Apache License 2.0.

## v0.11

* **Frontend authentication**: The Angular frontend now has full JWT authentication. Users must log in with email/password before accessing any page. Includes a login page, automatic token refresh, HTTP interceptor for attaching tokens to API requests, route guards that redirect unauthenticated users to login, and a Sign Out button in the sidebar. E2E tests use Playwright's global setup to authenticate once and share auth state across all tests.
* **Flask removal**: The legacy Flask manager service (`ezrules manager`) has been fully removed. The Angular frontend with FastAPI API v2 is now the sole interface.
* **Removed CLI commands**: `ezrules manager` and `ezrules evaluator` commands have been removed. Use `ezrules api` to start the service.
* **Removed dependencies**: Flask, Flask-Security-Too, Flask-WTF, Flask-CORS, Bootstrap-Flask, and pytz have been removed from the project dependencies. Gunicorn is retained for production deployments with uvicorn workers.
* **Standalone model mixins**: `AsaList`, `RoleMixin`, and `UserMixin` previously imported from flask_security are now defined directly in `ezrules.models.backend_core`, removing the flask_security dependency from the data model layer.
* **Removed Flask decorator**: The `requires_permission` Flask decorator in `ezrules.core.permissions` has been removed. The FastAPI API v2 uses its own `require_permission` dependency in `ezrules.backend.api_v2.auth.dependencies`.
* **Explicit versioning**: Replaced `history_meta.py` auto-versioning system with explicit `RuleHistory` and `RuleEngineConfigHistory` models. History snapshots are now created by helper functions (`save_rule_history`, `save_config_history`) before mutations, giving full control over when and how history is recorded.
* **Changed-by tracking**: Rule and configuration history entries now include a `changed_by` column that records who made each change (user email from API, `"cli"` from CLI commands). The Audit Trail page in the Angular frontend displays this in a new "Changed By" column.
* **Removed history_meta.py**: The SQLAlchemy event-listener-based `history_meta.py` module and all `versioned_session()` calls have been removed. Database tables must be recreated with `uv run ezrules init-db --auto-delete`.
* **Enhanced audit trail**: The audit trail now tracks changes to user lists (create, rename, delete, add/remove entries), outcomes (create, delete), and labels (create, delete) in addition to rules and configurations. Each audit entry records who performed the action and when. New API endpoints: `GET /api/v2/audit/user-lists`, `GET /api/v2/audit/outcomes`, `GET /api/v2/audit/labels`.
* **Accordion audit page**: The Audit Trail page has been redesigned with collapsible accordion sections for Rule History, Configuration History, User List History, Outcome History, and Label History. Sections are collapsed by default to reduce visual clutter. Action types are shown with color-coded badges (green for creates, red for deletes, blue for renames).

## v0.10

* **FastAPI Migration (In Progress)**: New API v2 service built on FastAPI for improved performance and modern async support
* **Evaluator merged into API service**: The standalone evaluator service (port 9999) has been merged into the main API service. Rule evaluation is now available at `/api/v2/evaluate` on port 8888. The `evaluator` CLI command is deprecated in favour of `api`.
* New CLI command `uv run ezrules api --port 8888` to start FastAPI server with optional `--reload` flag for development
* JWT authentication system (coming soon) - will support both local users and future OAuth/SSO integrations
* OpenAPI documentation automatically available at `/docs` (Swagger UI) and `/redoc`
* CORS configured for Angular development server (localhost:4200)
* **User Lists management page**: Angular frontend page for managing user lists and their entries. Accessible from the sidebar, supports creating/deleting lists, adding/removing entries with a master-detail layout. Backend API at `/api/v2/user-lists/`.
* **Database initialisation seeds default data**: `uv run ezrules init-db` now seeds default outcomes (RELEASE, HOLD, CANCEL) and default user lists (MiddleAsiaCountries, NACountries, LatamCountries) so rules using `@ListName` notation work out of the box.
* **Rule test endpoint accepts string outcomes**: The rule test endpoint (`POST /api/v2/rules/test`) now correctly handles rules that return string outcomes like `"HOLD"`, not just booleans.
* **Dashboard page**: Angular dashboard showing active rules count, transaction volume chart, and rule outcomes over time charts. Includes time range selector (1h, 6h, 12h, 24h, 30d). Accessible from sidebar and is the default landing page.
* **User Management admin panel**: Angular page at `/management/users` for managing user accounts. Supports creating users with optional role assignment, deleting users, toggling active/inactive status, admin-initiated password reset, and inline role assignment/removal. Accessible from sidebar "Security" link.
* **Role Management page**: Angular page at `/role_management` for managing roles. Supports creating roles with descriptions, assigning roles to users via dropdowns, removing roles from users, deleting roles (only when no users assigned), and links to per-role permission configuration. Accessible from sidebar "Settings" link.
* **Role Permissions page**: Angular page at `/role_management/{id}/permissions` for configuring per-role permissions. Displays all available permissions grouped by resource type with checkboxes, shows current permissions as green summary badges, and supports saving permission changes. Navigable from the Role Management page via "Manage Permissions" link.
* **Audit Trail page**: Angular page at `/audit` showing the history of rule and configuration changes. Displays two tables: Rule History (version, rule ID, description truncated to 100 chars, changed timestamp) and Configuration History (version, label, changed timestamp), each sorted by date descending. Accessible from the sidebar.

## v0.9

* Implementation of RBAC: per-resource access control, audit trail
* List and outcomes are now editable
* User management UI
* Role and permissions management UI
* Enhanced init-db script with interactive database management and --auto-delete option
* Transaction marking for analytics: mark transactions with true labels for fraud detection analysis
* Single event marking API endpoint (/mark-event) for programmatic labeling
* Bulk CSV upload interface for efficient batch labeling of events
* Enhanced CLI test data generation with realistic fraud patterns and label assignment
* Automatic default label creation (FRAUD, CHARGEBACK, NORMAL) for immediate testing
* Dashboard transaction volume chart with Chart.js: visualize transaction patterns over configurable time ranges
* Time aggregation options: 1 hour, 6 hours, 12 hours, 24 hours, and 30 days
* Real-time API endpoint for transaction volume data (/api/transaction_volume)
* **Label Analytics Dashboard**: Comprehensive analytics for ground truth labels with temporal analysis
* Total labeled events metric card tracking overall labeling coverage
* Individual time-series charts for each label type showing temporal trends over configurable time ranges
* Label analytics API endpoints: /api/labels_summary, /api/labels_distribution
* Configurable time ranges for label analytics (1h, 6h, 12h, 24h, 30d)
* Angular frontend revision navigation: clicking a rule revision link now navigates to a read-only view of that historical revision via GET /api/rules/<id>/revisions/<rev>
* **Outcomes management page**: Ported to Angular frontend. Users can list, create, and delete allowed outcomes via the new /outcomes page, reachable from the sidebar. Backend API endpoints added: GET/POST /api/outcomes, DELETE /api/outcomes/<name>
* **Label Analytics page ported to Angular frontend**: The /label_analytics page is now available in the Angular app, reachable via the sidebar "Analytics" link. Displays the total labeled events metric card and per-label time-series line charts powered by Chart.js, with a time range selector (1h, 6h, 12h, 24h, 30d) that updates charts in real time

## v0.7

* Migrated from Poetry to UV for faster dependency management
* Upgraded to Python 3.12 minimum requirement

## v0.6

* Ability to backtest rule changes: make change, submit for backtesting, check result
* Switch to pydantic-based settings management
* Transaction submitted for testing are now saved in the history table
* Rule evaluation results are now saved in the history table
* New CLI utilities to generate test data

## v0.5

* The app is compatible with AWS EKS
* Basic testing introduced
* Rule history is maintained through a history table
* Standalone scripts to init the db and add a user
* Internally, switch to poetry dependency management
* Manager and evaluator can run as executables

## v0.4

* RDBMS are now supported as a backend for rule configuration storage
* The application can now be deployed in a k8s cluster

## v0.3

* At-notation is available. Constructs of type `if $send_country in @Latam...`
* Users are now required to login to make changes to the rule set

## v0.2

* Dollar-notation can be used to refer to attributes, e.g. `if $amount>1000...`
* When you create a rule, you can now test it right away before deploying
* Outcomes of rules are now controlled against a list of allowed outcomes
* When a rule is edited, there is now a warning that someone else is working on it too
* Each rule revision now has a timestamp associated with it
* For rules with modification history, see the changelog with highlighted diffs

## v0.1

* A better documentation on rules writing
* Fixed a bug wherein the lambda rule executor was not properly configured with the environment variable
* Rule evaluator app now accepts lambda function name through an environment variable
* Rule manager fetched the s3 bucket name from an environment variable now
* Rule manager backend table name is now automatically configured with `DYNAMODB_RULE_MANAGER_TABLE_NAME` environment variable
* General code cleanup

## v0.0

* A single script that deploys application to AWS
* This is a first release, so all previous changes are squashed into it
