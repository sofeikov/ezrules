# API v2 Reference

ezrules now runs as a unified FastAPI service.

## Run Locally

--8<-- "snippets/start-api.md"

The API includes:

- Auth (`/api/v2/auth/*`)
- Rules (`/api/v2/rules/*`)
- Outcomes (`/api/v2/outcomes/*`)
- Labels (`/api/v2/labels/*`)
- Analytics (`/api/v2/analytics/*`)
- Users (`/api/v2/users/*`)
- Roles and permissions (`/api/v2/roles/*`)
- User lists (`/api/v2/user-lists/*`)
- Audit (`/api/v2/audit/*`)
- Backtesting (`/api/v2/backtesting/*`)
- Evaluator (`/api/v2/evaluate`)

## Live API Documentation (Recommended)

--8<-- "snippets/openapi-links.md"

These are generated directly from the running FastAPI app and are the canonical API docs.
