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
- `POST /api/v2/evaluate` requires either an `X-API-Key` header (recommended for service-to-service) or a valid Bearer token

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
| `GET` | `/api/v2/auth/me` | Bearer | Current user profile |

### Rules

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/rules` | Bearer + permission | List rules |
| `POST` | `/api/v2/rules` | Bearer + permission | Create rule |
| `GET` | `/api/v2/rules/{rule_id}` | Bearer + permission | Rule details |
| `GET` | `/api/v2/rules/{rule_id}/revisions/{revision_number}` | Bearer + permission | Specific historical revision |
| `PUT` | `/api/v2/rules/{rule_id}` | Bearer + permission | Update rule |
| `DELETE` | `/api/v2/rules/{rule_id}` | Bearer + `DELETE_RULE` | Delete rule |
| `POST` | `/api/v2/rules/{rule_id}/promote` | Bearer + `MODIFY_RULE` | Promote draft rule to active |
| `POST` | `/api/v2/rules/{rule_id}/archive` | Bearer + `MODIFY_RULE` | Archive rule |
| `POST` | `/api/v2/rules/{rule_id}/rollback` | Bearer + `MODIFY_RULE` | Create a new draft version from a historical revision (`revision_number` in body) |
| `POST` | `/api/v2/rules/verify` | Bearer + permission | Verify rule source and extracted params |
| `POST` | `/api/v2/rules/test` | Bearer + permission | Test rule payload |
| `GET` | `/api/v2/rules/{rule_id}/history` | Bearer + permission | Revision list |
| `POST` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Deploy rule to shadow |
| `DELETE` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Remove rule from shadow |
| `POST` | `/api/v2/rules/{rule_id}/shadow/promote` | Bearer + `MODIFY_RULE` | Promote shadow rule to production |

Rule lifecycle fields on rule responses:
- `status`: `draft`, `active`, or `archived`
- `effective_from`: activation timestamp for active versions
- `approved_by` / `approved_at`: approver audit metadata for promotions
- `POST /api/v2/rules` creates draft rules; `PUT /api/v2/rules/{id}` saves edits as draft and requires promotion to reactivate.
- `POST /api/v2/rules/{id}/rollback` restores the selected historical revision's logic and description into a brand new draft version, preserving the full revision chain.
- Rule audit entries (`GET /api/v2/audit/rules*`) now include `action` (`updated`, `promoted`, `deactivated`, `rolled_back`, `deleted`) and `to_status` to show lifecycle transitions such as `draft -> active`.
- Deleting a rule preserves its history so `GET /api/v2/audit/rules/{rule_id}` remains available after deletion.

### Shadow

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/shadow` | Bearer + `VIEW_RULES` | Current shadow config (rules + version) |
| `GET` | `/api/v2/shadow/results` | Bearer + `VIEW_RULES` | Recent shadow evaluation results (`?limit=50`) |
| `GET` | `/api/v2/shadow/stats` | Bearer + `VIEW_RULES` | Per-rule shadow vs production outcome comparison |

### Tested Events

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/tested-events` | Bearer + `VIEW_RULES` | Recent stored event evaluations with raw payload and triggered rules (`?limit=50`). Add `include_referenced_fields=true` to include each rule's referenced top-level fields. |

### Outcomes

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/outcomes` | Bearer + permission | List allowed outcomes in severity order |
| `POST` | `/api/v2/outcomes` | Bearer + permission | Create allowed outcome |
| `DELETE` | `/api/v2/outcomes/{outcome_name}` | Bearer + permission | Delete outcome |

### Labels

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/labels` | Bearer + permission | List labels |
| `POST` | `/api/v2/labels` | Bearer + permission | Create label |
| `POST` | `/api/v2/labels/bulk` | Bearer + permission | Create labels in bulk |
| `POST` | `/api/v2/labels/mark-event` | Bearer + permission | Mark single event |
| `POST` | `/api/v2/labels/upload` | Bearer + permission | CSV upload (`multipart/form-data`) |
| `DELETE` | `/api/v2/labels/{label_name}` | Bearer + permission | Delete label |

### Analytics

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/analytics/transaction-volume` | Bearer + permission | Time-series event volume |
| `GET` | `/api/v2/analytics/outcomes-distribution` | Bearer + permission | Outcome trends |
| `GET` | `/api/v2/analytics/labels-summary` | Bearer + permission | Total labeled summary |
| `GET` | `/api/v2/analytics/labels-distribution` | Bearer + permission | Label trends |
| `GET` | `/api/v2/analytics/labeled-transaction-volume` | Bearer + permission | Time-series labeled event volume |
| `GET` | `/api/v2/analytics/rule-quality` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Synchronous snapshot precision/recall report for configured curated pairs (includes `freeze_at`) |
| `POST` | `/api/v2/analytics/rule-quality/reports` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Return existing snapshot by filters, or generate a new one only when `force_refresh=true` |
| `GET` | `/api/v2/analytics/rule-quality/reports/{report_id}` | Bearer + `VIEW_RULES` + `VIEW_LABELS` | Poll async report status/result |

Rule quality query params:
- `min_support` (default `1`)
- `lookback_days` (optional; defaults to runtime setting)
- `force_refresh` on report requests: `false` returns existing snapshot only, `true` enqueues a new snapshot
- `freeze_at` is returned in responses to indicate snapshot timestamp
- Reports include only active curated pairs configured under Settings.

### Settings

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/settings/runtime` | Bearer + `VIEW_ROLES` | Read runtime settings |
| `PUT` | `/api/v2/settings/runtime` | Bearer + `MANAGE_PERMISSIONS` | Update runtime settings (e.g., rule quality lookback days) |
| `GET` | `/api/v2/settings/outcome-hierarchy` | Bearer + `VIEW_ROLES` | Read ordered outcome severity hierarchy |
| `PUT` | `/api/v2/settings/outcome-hierarchy` | Bearer + `MANAGE_PERMISSIONS` | Replace ordered outcome severity hierarchy |
| `GET` | `/api/v2/settings/rule-quality-pairs` | Bearer + `VIEW_ROLES` | List configured curated outcome→label pairs |
| `GET` | `/api/v2/settings/rule-quality-pairs/options` | Bearer + `VIEW_ROLES` | List available outcomes and labels for pair creation |
| `POST` | `/api/v2/settings/rule-quality-pairs` | Bearer + `MANAGE_PERMISSIONS` | Create curated pair |
| `PUT` | `/api/v2/settings/rule-quality-pairs/{pair_id}` | Bearer + `MANAGE_PERMISSIONS` | Toggle pair active/inactive |
| `DELETE` | `/api/v2/settings/rule-quality-pairs/{pair_id}` | Bearer + `MANAGE_PERMISSIONS` | Delete curated pair |

Outcome hierarchy notes:
- Outcome hierarchy is ordered from highest severity to lowest severity.
- `POST /api/v2/evaluate` uses this hierarchy to compute the single `resolved_outcome` stored for each event.

### Users and Roles

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/users` | Bearer + permission | List users |
| `GET` | `/api/v2/users/{user_id}` | Bearer + permission | Get user details |
| `POST` | `/api/v2/users` | Bearer + permission | Create user |
| `POST` | `/api/v2/users/invite` | Bearer + permission | Invite user by email and send activation link |
| `PUT` | `/api/v2/users/{user_id}` | Bearer + permission | Update user |
| `DELETE` | `/api/v2/users/{user_id}` | Bearer + permission | Delete user |
| `POST` | `/api/v2/users/{user_id}/roles` | Bearer + permission | Assign role to user |
| `DELETE` | `/api/v2/users/{user_id}/roles/{role_id}` | Bearer + permission | Remove role from user |
| `GET` | `/api/v2/roles/permissions` | Bearer + permission | List all available permissions |
| `GET` | `/api/v2/roles` | Bearer + permission | List roles |
| `GET` | `/api/v2/roles/{role_id}` | Bearer + permission | Get role details |
| `POST` | `/api/v2/roles` | Bearer + permission | Create role |
| `PUT` | `/api/v2/roles/{role_id}` | Bearer + permission | Update role |
| `DELETE` | `/api/v2/roles/{role_id}` | Bearer + permission | Delete role |
| `GET` | `/api/v2/roles/{role_id}/permissions` | Bearer + permission | Get role permissions |
| `PUT` | `/api/v2/roles/{role_id}/permissions` | Bearer + permission | Update role permissions |

### User Lists

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/user-lists` | Bearer + permission | List user lists |
| `GET` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Get user list details |
| `POST` | `/api/v2/user-lists` | Bearer + permission | Create user list |
| `PUT` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Update list metadata |
| `DELETE` | `/api/v2/user-lists/{list_id}` | Bearer + permission | Delete list |
| `GET` | `/api/v2/user-lists/{list_id}/entries` | Bearer + permission | Get list entries |
| `POST` | `/api/v2/user-lists/{list_id}/entries` | Bearer + permission | Add one entry |
| `POST` | `/api/v2/user-lists/{list_id}/entries/bulk` | Bearer + permission | Add entries in bulk |
| `DELETE` | `/api/v2/user-lists/{list_id}/entries/{entry_id}` | Bearer + permission | Remove one entry |

### Field Types

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/field-types` | Bearer + permission | List all configured field types |
| `GET` | `/api/v2/field-types/observations` | Bearer + permission | List auto-discovered field observations |
| `POST` | `/api/v2/field-types` | Bearer + permission | Create or update a field type config (upsert) |
| `PUT` | `/api/v2/field-types/{field_name}` | Bearer + permission | Update type or datetime format for existing config |
| `DELETE` | `/api/v2/field-types/{field_name}` | Bearer + permission | Delete a field type config |

### Audit

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/audit` | Bearer + permission | Summary |
| `GET` | `/api/v2/audit/rules` | Bearer + permission | Rule history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/rules/{rule_id}` | Bearer + permission | Full history for one rule |
| `GET` | `/api/v2/audit/config` | Bearer + permission | Config history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/user-lists` | Bearer + permission | User-list history |
| `GET` | `/api/v2/audit/outcomes` | Bearer + permission | Outcome history |
| `GET` | `/api/v2/audit/labels` | Bearer + permission | Label history |
| `GET` | `/api/v2/audit/users` | Bearer + permission | User-account history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/roles` | Bearer + permission | Role/permission history (`limit`, `offset`, filters) |
| `GET` | `/api/v2/audit/field-types` | Bearer + permission | Field type config history (`limit`, `offset`, `field_name` filter) |

### Backtesting

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/backtesting` | Bearer + permission | Trigger async backtest |
| `GET` | `/api/v2/backtesting/task/{task_id}` | Bearer + permission | Task status/result |
| `GET` | `/api/v2/backtesting/{rule_id}` | Bearer + permission | Backtest history for rule |

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

## API Conventions

- JSON endpoints use `application/json`
- CSV upload endpoint uses `multipart/form-data`
- Analytics `aggregation` must be one of: `1h`, `6h`, `12h`, `24h`, `30d`
- Audit endpoints support pagination via `limit` and `offset`
- Validation errors use HTTP `422` with `detail`

## Live API Documentation (Canonical)

--8<-- "snippets/openapi-links.md"
