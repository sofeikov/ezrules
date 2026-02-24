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
- `POST /api/v2/evaluate` is internal/service oriented and currently does not require user auth

## Endpoint Map

### Authentication

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/auth/login` | No | OAuth2 form login |
| `POST` | `/api/v2/auth/refresh` | No (refresh token in body) | Exchanges refresh token |
| `GET` | `/api/v2/auth/me` | Bearer | Current user profile |

### Rules

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/rules` | Bearer + permission | List rules |
| `POST` | `/api/v2/rules` | Bearer + permission | Create rule |
| `GET` | `/api/v2/rules/{rule_id}` | Bearer + permission | Rule details |
| `GET` | `/api/v2/rules/{rule_id}/revisions/{revision_number}` | Bearer + permission | Specific historical revision |
| `PUT` | `/api/v2/rules/{rule_id}` | Bearer + permission | Update rule |
| `POST` | `/api/v2/rules/verify` | Bearer + permission | Verify rule source and extracted params |
| `POST` | `/api/v2/rules/test` | Bearer + permission | Test rule payload |
| `GET` | `/api/v2/rules/{rule_id}/history` | Bearer + permission | Revision list |
| `POST` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Deploy rule to shadow |
| `DELETE` | `/api/v2/rules/{rule_id}/shadow` | Bearer + `MODIFY_RULE` | Remove rule from shadow |
| `POST` | `/api/v2/rules/{rule_id}/shadow/promote` | Bearer + `MODIFY_RULE` | Promote shadow rule to production |

### Shadow

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/shadow` | Bearer + `VIEW_RULES` | Current shadow config (rules + version) |
| `GET` | `/api/v2/shadow/results` | Bearer + `VIEW_RULES` | Recent shadow evaluation results (`?limit=50`) |

### Outcomes

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/outcomes` | Bearer + permission | List allowed outcomes |
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

### Users and Roles

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/v2/users` | Bearer + permission | List users |
| `GET` | `/api/v2/users/{user_id}` | Bearer + permission | Get user details |
| `POST` | `/api/v2/users` | Bearer + permission | Create user |
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

### Evaluator

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/v2/evaluate` | Internal/service | Evaluate one event against active rules |

## API Conventions

- JSON endpoints use `application/json`
- CSV upload endpoint uses `multipart/form-data`
- Analytics `aggregation` must be one of: `1h`, `6h`, `12h`, `24h`, `30d`
- Audit endpoints support pagination via `limit` and `offset`
- Validation errors use HTTP `422` with `detail`

## Live API Documentation (Canonical)

--8<-- "snippets/openapi-links.md"
