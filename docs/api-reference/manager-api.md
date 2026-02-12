# API v2 Reference

This page is a high-level map of the API surface.
For full request/response schemas, use the generated OpenAPI docs.

## Run Locally

--8<-- "snippets/start-api.md"

## Authentication Model

- `POST /api/v2/auth/login`: no token required
- `POST /api/v2/auth/refresh`: requires refresh token
- Most `/api/v2/*` endpoints: require `Authorization: Bearer <access_token>`
- `POST /api/v2/evaluate`: designed for internal/service use and currently does not require user auth

## Endpoint Groups

| Group | Base Path | Auth | Typical Use |
|---|---|---|---|
| Auth | `/api/v2/auth/*` | Mixed | Login, token refresh, current user |
| Rules | `/api/v2/rules/*` | Bearer + permissions | Create, update, test, history |
| Outcomes | `/api/v2/outcomes/*` | Bearer + permissions | Manage allowed outcomes |
| Labels | `/api/v2/labels/*` | Bearer + permissions | Create labels, mark events, CSV upload |
| Analytics | `/api/v2/analytics/*` | Bearer + permissions | Dashboard and label analytics |
| Users | `/api/v2/users/*` | Bearer + permissions | User lifecycle, role assignment |
| Roles | `/api/v2/roles/*` | Bearer + permissions | Role and permission management |
| User Lists | `/api/v2/user-lists/*` | Bearer + permissions | List definitions and entries |
| Audit | `/api/v2/audit/*` | Bearer + permissions | History and change attribution |
| Backtesting | `/api/v2/backtesting/*` | Bearer + permissions | Trigger and inspect backtests |
| Evaluator | `/api/v2/evaluate` | Internal/service | Evaluate events against active rules |

## Frequently Used Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v2/auth/login` | Exchange email/password for access and refresh tokens |
| `GET` | `/api/v2/rules` | List rules |
| `POST` | `/api/v2/rules` | Create rule |
| `POST` | `/api/v2/rules/test` | Test rule logic with sample payload |
| `GET` | `/api/v2/outcomes` | List allowed outcomes |
| `POST` | `/api/v2/labels/mark-event` | Apply label to one event |
| `POST` | `/api/v2/labels/upload` | Upload CSV labels |
| `GET` | `/api/v2/analytics/transaction-volume` | Chart data by aggregation window |
| `GET` | `/api/v2/audit/rules` | Rule audit history (`limit`, `offset`, filters) |
| `POST` | `/api/v2/backtesting` | Trigger backtest task |
| `GET` | `/api/v2/backtesting/task/{task_id}` | Poll async backtest status |

## API Conventions

- Content type: `application/json` unless endpoint expects multipart upload (for example `/api/v2/labels/upload`)
- Analytics aggregation values: `1h`, `6h`, `12h`, `24h`, `30d`
- Audit endpoints support pagination via `limit` and `offset`
- Validation errors return HTTP `422` with a `detail` payload

## Live API Documentation (Canonical)

--8<-- "snippets/openapi-links.md"
