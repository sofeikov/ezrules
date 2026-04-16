# API v2 Reference

This page provides a scannable endpoint map.
Use OpenAPI docs as the canonical request/response schema source.

## Run Locally

--8<-- "snippets/start-api.md"

## Authentication Contract

### Login endpoint format (important)

- Endpoint: `POST /api/v2/auth/login`
- Payload type: `application/x-www-form-urlencoded`
- Required fields:
  - `username` (email)
  - `password`

Example:

```bash
curl -X POST http://localhost:8888/api/v2/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin"
```

### Token usage

- Send access token as `Authorization: Bearer <access_token>`
- Access tokens include an `org_id` claim. Manager requests reject tokens whose `org_id` no longer matches the authenticated user's stored organisation.
- `POST /api/v2/evaluate` requires either an `X-API-Key` header (recommended for service-to-service) or a valid Bearer token

### Organisation scoping

- Users belong to exactly one organisation.
- The current organisation for manager requests comes from the authenticated user, not a request body parameter.
- Manager routes now scope rules, tested events, shadow, outcomes, users, roles, labels, user lists, field types, settings, analytics, API keys, backtesting history, and audit/history reads to the caller's organisation.
- Roles and labels are organisation-owned catalogs, so the same role/label names can exist in different organisations.
- User-role assignment is same-org only.

### Session revocation (logout)

Refresh tokens are tracked server-side in the `user_session` table. To revoke a session:

```bash
curl -X POST http://localhost:8888/api/v2/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

After a successful logout, the refresh token is deleted from the database and any subsequent attempt to use it returns `401`. Access tokens remain valid until their 30-minute expiry (stateless JWTs cannot be revoked).

### Refresh token rotation

Each call to `POST /api/v2/auth/refresh` deletes the submitted refresh token and issues a new one. A refresh token can only be used once. Presenting a previously-used or revoked refresh token returns `401 Session not found or already revoked`.

## Endpoint Map

### Authentication

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/auth/login` | No | OAuth2 form login |
| `POST` | `/api/v2/auth/accept-invite` | No | Accept invitation token and set password |
| `POST` | `/api/v2/auth/forgot-password` | No | Send password reset email (always generic response) |
| `POST` | `/api/v2/auth/reset-password` | No | Reset password using one-time token |
| `POST` | `/api/v2/auth/refresh` | No (refresh token in body) | Exchanges refresh token (rotation — one-time use) |
| `POST` | `/api/v2/auth/logout` | Bearer + refresh token in body | Revokes refresh token server-side |
| `GET` | `/api/v2/auth/me` | Bearer | Current user profile, including effective permission names |

### Rules

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/rules` | Bearer + permission | List rules |
| `POST` | `/api/v2/rules` | Bearer + permission | Create rule |
| `GET` | `/api/v2/rules/{rule_id}` | Bearer + permission | Rule details |
| `GET` | `/api/v2/rules/{rule_id}/revisions/{revision_number}` | Bearer + permission | Specific historical revision |
| `PUT` | `/api/v2/rules/{rule_id}` | Bearer + permission | Update rule |
| `PUT` | `/api/v2/rules/main-order` | Bearer + `REORDER_RULES` | Replace the full ordered main-rule sequence |
| `DELETE` | `/api/v2/rules/{rule_id}` | Bearer + `DELETE_RULE` | Delete rule |
| `POST` | `/api/v2/rules/{rule_id}/promote` | Bearer + `PROMOTE_RULES` | Promote draft rule to active |
| `POST` | `/api/v2/rules/{rule_id}/pause` | Bearer + `PAUSE_RULES` | Pause active rule |
| `POST` | `/api/v2/rules/{rule_id}/resume` | Bearer + `PROMOTE_RULES` | Resume paused rule to active |
| `POST` | `/api/v2/rules/{rule_id}/archive` | Bearer + `MODIFY_RULE` | Archive rule |
| `POST` | `/api/v2/rules/{rule_id}/rollback` | Bearer + `MODIFY_RULE` | Create a new draft version from a historical revision (`revision_number` in body) |
| `POST` | `/api/v2/rules/verify` | Bearer + permission | Verify rule source, extracted params, and advisory warnings for unseen fields |
| `POST` | `/api/v2/rules/test` | Bearer + permission | Test rule payload |
| `GET` | `/api/v2/rules/{rule_id}/history` | Bearer + permission | Revision list |
| `POST` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Deploy rule to shadow |
| `DELETE` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Remove rule from shadow |
| `POST` | `/api/v2/rules/{rule_id}/shadow/promote` | Bearer + `PROMOTE_RULES` | Promote shadow rule to production |
| `POST` | `/api/v2/rules/{rule_id}/rollout` | Bearer + `PROMOTE_RULES` | Start or update a live traffic rollout for an active rule |
| `DELETE` | `/api/v2/rules/{rule_id}/rollout` | Bearer + `PROMOTE_RULES` | Remove a rollout |
| `POST` | `/api/v2/rules/{rule_id}/rollout/promote` | Bearer + `PROMOTE_RULES` | Promote rollout candidate to full production |

Rule lifecycle fields on rule responses:
- `status`: `draft`, `active`, `paused`, or `archived`
- `evaluation_lane`: `main` or `allowlist`
- `execution_order`: integer serving order used by main rules; lower values run earlier
- `effective_from`: activation timestamp for active versions
- `approved_by` / `approved_at`: approver audit metadata for promotions
- `POST /api/v2/rules` creates draft rules.
- `PUT /api/v2/rules/{id}` saves edits as draft by default and requires promotion to reactivate.
- `POST /api/v2/rules/{id}/pause` moves an active rule out of live production evaluation without archiving it.
- `POST /api/v2/rules/{id}/resume` returns a paused rule to `active` and records fresh approver metadata.
- Editing a paused rule keeps it paused; it does not silently reactivate.
- If runtime setting `auto_promote_active_rule_updates` is enabled for the caller's org, editing an already active rule keeps it active and updates production immediately, but the caller still needs `PROMOTE_RULES`.
- `POST /api/v2/rules/{id}/rollback` restores the selected historical revision's logic and description into a brand new draft version, preserving the full revision chain.
- Rule audit entries (`GET /api/v2/audit/rules*`) now include `action` (`updated`, `reordered`, `promoted`, `paused`, `resumed`, `deactivated`, `rolled_back`, `deleted`), `execution_order`, and `to_status` to show lifecycle transitions such as `draft -> active` or `active -> paused`.
- Deleting a rule preserves its history so `GET /api/v2/audit/rules/{rule_id}` remains available after deletion.
- Rules with an active shadow deployment or rollout cannot be edited, paused, archived, deleted, directly promoted, resumed, or rolled back until the candidate deployment is removed or promoted.
- Allowlist rules are first-class production rules. They cannot be deployed to shadow or rollout.

`POST /api/v2/rules/verify` response fields:
- `valid`: `true` when the rule compiles successfully; `false` when syntax or referenced-list validation fails.
- `params`: extracted `$field` references used for JSON prefill and unseen-field warnings.
- `warnings`: advisory messages for referenced fields that have not yet been observed in traffic or rule-test payloads.
- `referenced_lists`: detected `@user_list` names, even when validation fails.
- `errors`: structured validation failures with `message`, `line`, `column`, `end_line`, and `end_column`.

### Shadow

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/shadow` | Bearer + `VIEW_RULES` | Current shadow config (rules + version) |
| `GET` | `/api/v2/shadow/results` | Bearer + `VIEW_RULES` | Recent shadow evaluation results (`?limit=50`) |
| `GET` | `/api/v2/shadow/stats` | Bearer + `VIEW_RULES` | Per-rule shadow vs production outcome comparison |

### Rollouts

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/rollouts` | Bearer + `VIEW_RULES` | Current rollout config (rules + traffic percent + version) |
| `GET` | `/api/v2/rollouts/results` | Bearer + `VIEW_RULES` | Recent rollout comparison records (`?limit=50`) |
| `GET` | `/api/v2/rollouts/stats` | Bearer + `VIEW_RULES` | Per-rule candidate vs control outcomes plus served split counts |

### Tested Events

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/tested-events` | Bearer + `VIEW_RULES` | Recent stored event evaluations with uploaded `label_name`, raw payload, and triggered rules (`?limit=50`). Add `include_referenced_fields=true` to include each rule's referenced top-level fields. |

### Outcomes

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/outcomes` | Bearer + permission | List allowed outcomes in severity order for the caller's org |
| `POST` | `/api/v2/outcomes` | Bearer + permission | Create allowed outcome in the caller's org |
| `DELETE` | `/api/v2/outcomes/{outcome_name}` | Bearer + permission | Delete outcome from the caller's org |

### Labels

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/labels` | Bearer + permission | List labels in the caller's org |
| `POST` | `/api/v2/labels` | Bearer + permission | Create label in the caller's org |
| `POST` | `/api/v2/labels/bulk` | Bearer + permission | Create labels in bulk in the caller's org |
| `POST` | `/api/v2/labels/mark-event` | Bearer + permission | Mark single event in the caller's org; returns `409` if that org has duplicate `event_id`s |
| `POST` | `/api/v2/labels/upload` | Bearer + permission | CSV upload for events in the caller's org (`multipart/form-data`) with row-level success/error reporting |
| `DELETE` | `/api/v2/labels/{label_name}` | Bearer + permission | Delete label from the caller's org |

### Analytics

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/analytics/transaction-volume` | Bearer + permission | Time-series event volume |
| `GET` | `/api/v2/analytics/outcomes-distribution` | Bearer + permission | Outcome trends |
| `GET` | `/api/v2/analytics/rule-activity` | Bearer + `VIEW_RULES` | Most/least firing active rules for the caller's org; counts stored non-null outcomes and includes zero-hit active rules in the least-firing ranking |
| `GET` | `/api/v2/analytics/labels-summary` | Bearer + permission | Total labeled summary for the caller's org |
| `GET` | `/api/v2/analytics/labels-distribution` | Bearer + permission | Label trends for the caller's org |
| `GET` | `/api/v2/analytics/labeled-transaction-volume` | Bearer + permission | Time-series labeled event volume for the caller's org |
| `GET` | `/api/v2/analytics/rule-quality` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Synchronous snapshot precision/recall report for configured curated pairs (includes `freeze_at`) |
| `POST` | `/api/v2/analytics/rule-quality/reports` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Return existing snapshot by filters, or generate a new one only when `force_refresh=true` |
| `GET` | `/api/v2/analytics/rule-quality/reports/{report_id}` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Poll async report status/result |

Rule quality query params:
- `min_support` (default `1`)
- `lookback_days` (optional; defaults to runtime setting)
- `force_refresh` on report requests: `false` returns existing snapshot only, `true` enqueues a new snapshot
- `freeze_at` is returned in responses to indicate snapshot timestamp
- Reports include only active curated pairs configured under Settings.

Rule activity query params:
- `aggregation` (default `6h`; valid values `1h`, `6h`, `12h`, `24h`, `30d`)
- `limit` (default `5`; maximum rules returned per ranking)

### Settings

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/settings/runtime` | Bearer + `VIEW_ROLES` | Read runtime settings |
| `PUT` | `/api/v2/settings/runtime` | Bearer + field-specific permission | Update runtime settings. `MANAGE_PERMISSIONS` covers general runtime settings; `MANAGE_NEUTRAL_OUTCOME` is required when changing `neutral_outcome`. |
| `GET` | `/api/v2/settings/outcome-hierarchy` | Bearer + `VIEW_ROLES` | Read ordered outcome severity hierarchy |
| `PUT` | `/api/v2/settings/outcome-hierarchy` | Bearer + `MANAGE_PERMISSIONS` | Replace ordered outcome severity hierarchy |
| `GET` | `/api/v2/settings/rule-quality-pairs` | Bearer + `VIEW_ROLES` | List configured curated outcome→label pairs |
| `GET` | `/api/v2/settings/rule-quality-pairs/options` | Bearer + `VIEW_ROLES` | List available outcomes and labels for pair creation in the caller's org |
| `POST` | `/api/v2/settings/rule-quality-pairs` | Bearer + `MANAGE_PERMISSIONS` | Create curated pair |
| `PUT` | `/api/v2/settings/rule-quality-pairs/{pair_id}` | Bearer + `MANAGE_PERMISSIONS` | Toggle pair active/inactive |
| `DELETE` | `/api/v2/settings/rule-quality-pairs/{pair_id}` | Bearer + `MANAGE_PERMISSIONS` | Delete curated pair |

Outcome hierarchy notes:
- Outcome hierarchy is ordered from highest severity to lowest severity.
- `POST /api/v2/evaluate` uses this hierarchy to compute the single `resolved_outcome` stored for each event.

Runtime settings notes:
- `GET /api/v2/settings/runtime` returns both stored values and fallback defaults for `rule_quality_lookback_days`, `auto_promote_active_rule_updates`, `main_rule_execution_mode`, and `neutral_outcome`.
- `auto_promote_active_rule_updates` defaults to `false`.
- `main_rule_execution_mode` defaults to `all_matches` and can be switched to `first_match` for the main rule lane only.
- `neutral_outcome` defaults to `RELEASE` and must match an existing configured outcome; allowlist rules return it as `!RELEASE`.
- Runtime settings responses also include `invalid_allowlist_rules`, a list of existing allowlist rules that no longer comply with the selected neutral outcome.
- Neutral-outcome changes are recorded in outcome audit history with action `neutral_outcome_updated`.
- When `auto_promote_active_rule_updates=true`, saving edits to an active rule requires both `MODIFY_RULE` and `PROMOTE_RULES`.

### Users and Roles

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/users` | Bearer + permission | List users in the caller's org |
| `GET` | `/api/v2/users/{user_id}` | Bearer + permission | Get user details in the caller's org |
| `POST` | `/api/v2/users` | Bearer + permission | Create user in the caller's org |
| `POST` | `/api/v2/users/invite` | Bearer + permission | Invite user into the caller's org and send activation link |
| `PUT` | `/api/v2/users/{user_id}` | Bearer + permission | Update user in the caller's org |
| `DELETE` | `/api/v2/users/{user_id}` | Bearer + permission | Delete user in the caller's org |
| `POST` | `/api/v2/users/{user_id}/roles` | Bearer + permission | Assign role to user in the caller's org (cross-org role IDs return `404`) |
| `DELETE` | `/api/v2/users/{user_id}/roles/{role_id}` | Bearer + permission | Remove role from user in the caller's org |
| `GET` | `/api/v2/roles/permissions` | Bearer + permission | List all available permissions |
| `GET` | `/api/v2/roles` | Bearer + permission | List roles in the caller's org |
| `GET` | `/api/v2/roles/{role_id}` | Bearer + permission | Get role details in the caller's org |
| `POST` | `/api/v2/roles` | Bearer + permission | Create role in the caller's org |
| `PUT` | `/api/v2/roles/{role_id}` | Bearer + permission | Update role in the caller's org |
| `DELETE` | `/api/v2/roles/{role_id}` | Bearer + permission | Delete role from the caller's org |
| `GET` | `/api/v2/roles/{role_id}/permissions` | Bearer + permission | Get role permissions in the caller's org |
| `PUT` | `/api/v2/roles/{role_id}/permissions` | Bearer + permission | Update role permissions in the caller's org |

### User Lists

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/user-lists` | Bearer + permission | List user lists in the caller's org |
| `GET` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Get user list details in the caller's org |
| `POST` | `/api/v2/user-lists` | Bearer + permission | Create user list in the caller's org |
| `PUT` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Update list metadata in the caller's org |
| `DELETE` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Delete list in the caller's org |
| `GET` | `/api/v2/user-lists/{list_id}/entries` | Bearer + permission | Get list entries in the caller's org |
| `POST` | `/api/v2/user-lists/{list_id}/entries` | Bearer + permission | Add one entry in the caller's org |
| `POST` | `/api/v2/user-lists/{list_id}/entries/bulk` | Bearer + permission | Add entries in bulk in the caller's org |
| `DELETE` | `/api/v2/user-lists/{list_id}/entries/{entry_id}` | Bearer + permission | Remove one entry from the caller's org list |

### Field Types

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/field-types` | Bearer + permission | List all configured field types for the caller's org |
| `GET` | `/api/v2/field-types/observations` | Bearer + permission | List auto-discovered field observations for the caller's org |
| `POST` | `/api/v2/field-types` | Bearer + permission | Create or update a field type config (upsert) in the caller's org, including `required` |
| `PUT` | `/api/v2/field-types/{field_name}` | Bearer + permission | Update type, `required`, or datetime format for existing config in the caller's org |
| `DELETE` | `/api/v2/field-types/{field_name}` | Bearer + permission | Delete a field type config from the caller's org |

Field type config note:
- Config payloads now include `required: bool`. When `required=true`, live evaluation rejects events where that field is missing or `null`.

### Audit

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/audit` | Bearer + permission | Summary for the caller's org |
| `GET` | `/api/v2/audit/rules` | Bearer + permission | Rule history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/rules/{rule_id}` | Bearer + permission | Full history for one rule |
| `GET` | `/api/v2/audit/config` | Bearer + permission | Config history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/user-lists` | Bearer + permission | User-list history |
| `GET` | `/api/v2/audit/outcomes` | Bearer + permission | Outcome history |
| `GET` | `/api/v2/audit/labels` | Bearer + permission | Label history for the caller's org, including manual/CSV assignment details |
| `GET` | `/api/v2/audit/users` | Bearer + permission | User-account history for the caller's org (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/roles` | Bearer + permission | Role/permission history for the caller's org (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/field-types` | Bearer + permission | Field type config history (`limit`, `offset`, `field_name` filter) |
| `GET` | `/api/v2/audit/api-keys` | Bearer + permission | API key create/revoke history for the caller's org (`limit`, `offset`, filters) |

### Backtesting

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/backtesting` | Bearer + permission | Trigger async backtest for a rule in the caller's org |
| `DELETE` | `/api/v2/backtesting/{task_id}` | Bearer + permission | Cancel a queued or running backtest task and persist it as `cancelled` |
| `POST` | `/api/v2/backtesting/{task_id}/retry` | Bearer + permission | Retry a failed/cancelled backtest using the stored logic snapshot |
| `GET` | `/api/v2/backtesting/task/{task_id}` | Bearer + permission | Task status/result, including outcome counts/rates, `eligible_records`, `skipped_records`, warnings, plus label counts and quality metrics for labeled history |
| `GET` | `/api/v2/backtesting/{rule_id}` | Bearer + permission | Backtest history for a rule visible to the caller's org |

Backtest task result note:
- `GET /api/v2/backtesting/task/{task_id}` now returns both the legacy terminal `status` (`PENDING`, `SUCCESS`, `FAILURE`, `CANCELLED`) and a persisted `queue_status` (`pending`, `running`, `done`, `failed`, `cancelled`) so UI clients can distinguish queued work from active execution.
- Backtest history rows now persist `queue_status`, `completed_at`, and the full result payload in `result_metrics`, so completed jobs remain inspectable even after Celery result-backend entries age out.
- `GET /api/v2/backtesting/task/{task_id}` returns raw outcome counts/rates over the eligible comparison subset used by both stored and proposed logic.
- Results now include `eligible_records`, `skipped_records`, and `warnings` when historical records were excluded because a referenced field was missing/null or live normalization rules would have rejected the event.
- When labeled historical events exist, it also returns `labeled_records`, `label_counts`, and stored/proposed outcome→label quality summaries and pair metrics (`precision`, `recall`, `f1`, `true_positive`, `false_positive`, `false_negative`).
- Backtest workers derive organisation context from the selected rule/request rather than a fixed app-wide org setting.

### API Keys

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/api-keys` | Bearer + `MANAGE_API_KEYS` | Create API key (raw key returned once) |
| `GET` | `/api/v2/api-keys` | Bearer + `MANAGE_API_KEYS` | List active API keys (no raw key) |
| `DELETE` | `/api/v2/api-keys/{gid}` | Bearer + `MANAGE_API_KEYS` | Revoke API key |

### Evaluator

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/evaluate` | API key or Bearer | Evaluate one event against active rules |

Evaluator storage note:
- `POST /api/v2/evaluate` persists events and per-rule results, which can then be reviewed via `GET /api/v2/tested-events`.
- If required-field validation or strict rule lookup fails, the request returns `400` and nothing is persisted.

## API Conventions

- JSON endpoints use `application/json`
- CSV upload endpoint uses `multipart/form-data`
- Analytics `aggregation` must be one of: `1h`, `6h`, `12h`, `24h`, `30d`
- Audit endpoints support pagination via `limit` and `offset`
- Validation errors use HTTP `422` with `detail`

## Live API Documentation (Canonical)

--8<-- "snippets/openapi-links.md"
