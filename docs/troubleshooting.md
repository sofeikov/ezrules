# Troubleshooting

Use this page as the default entry point when local setup, rule testing, or analytics behavior looks wrong.

## API service does not start

**Likely causes**

- `EZRULES_DB_ENDPOINT` is missing or invalid
- PostgreSQL is not running or credentials are wrong
- Port `8888` is already in use

**Diagnose**

```bash
docker compose ps
uv run ezrules api --port 8888
lsof -i :8888
```

**Fix**

1. Start infrastructure: `docker compose up -d`
2. Confirm connection settings in `settings.env`
3. Stop the conflicting process or run API on another port

**Verify**

- `http://localhost:8888/ping` returns a success response
- `http://localhost:8888/docs` opens

## Cannot log in to the frontend

**Likely causes**

- No user exists yet
- Wrong password
- API is down, so auth endpoints are unavailable

**Fix**

1. Create an admin user:

   ```bash
   uv run ezrules add-user --user-email admin@example.com --password admin --admin
   ```

2. Restart API service
3. Retry login on `http://localhost:4200/login`

## API returns `401` Unauthorized

**Likely causes**

- Missing `Authorization: Bearer <access_token>` header
- Expired access token
- Invalid credentials used during login

**Diagnose**

1. Re-run login and confirm token is returned
2. Confirm header format includes `Bearer` prefix
3. Check whether token refresh/login flow is still valid

**Fix**

1. Obtain a fresh access token from `/api/v2/auth/login`
2. Retry request with updated bearer token
3. If login itself fails, verify email/password and user active status

## API returns `403` Forbidden

**Likely causes**

- User is authenticated but lacks required permission
- Role does not include action needed by endpoint

**Diagnose**

1. Confirm endpoint being called (for example users, roles, audit)
2. Verify user role assignment in **Security** / **Settings**
3. Check role permissions for the relevant resource

**Fix**

1. Assign role with required permission
2. Or update role permissions for the target action
3. Retry with user account that has expected privileges

## Login request returns `422`

**Likely causes**

- Login payload sent as JSON instead of OAuth2 form fields

**Fix**

Use form-encoded payload:

```bash
curl -X POST http://localhost:8888/api/v2/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin"
```

## Rule does not fire

**Likely causes**

- Rule condition does not match payload fields
- Returned outcome is not in allowed outcomes
- Rule was not saved or tested against realistic payload

**Diagnose**

1. Open **Rules**, then open the rule detail page
2. Use **Test Rule** with the exact payload used in your API call
3. Inspect `rule_results`, `outcome_counters`, and `outcome_set` in `/api/v2/evaluate` response

**Fix**

1. Add missing outcome in **Outcomes** first
2. Validate payload field names (`$amount`, `$user_id`, etc.)
3. Save and retest with realistic values

## Analytics charts are empty

**Likely causes**

- No evaluated events in the selected time range
- Rules return no outcomes
- Events are not labeled yet (for label analytics)
- Invalid `aggregation` query value

**Diagnose**

```bash
curl "http://localhost:8888/api/v2/analytics/transaction-volume?aggregation=24h"
curl "http://localhost:8888/api/v2/analytics/outcomes-distribution?aggregation=24h"
curl "http://localhost:8888/api/v2/analytics/labels-summary"
```

**Fix**

1. Submit fresh evaluation events
2. Confirm outcomes exist and rules return those outcomes
3. Label events through `POST /api/v2/labels/mark-event`
4. Use supported aggregation values: `1h`, `6h`, `12h`, `24h`, `30d`

## Backtests stay in `PENDING`

**Likely causes**

- Celery worker is not running
- Redis broker is unavailable

**Diagnose**

```bash
docker compose ps
```

**Fix**

1. Start infrastructure with `docker compose up -d`
2. If running manually, start worker:

   ```bash
   uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
   ```

## Need deeper setup guidance?

- [Installation](getting-started/installation.md)
- [Configuration](getting-started/configuration.md)
- [Quick Start](getting-started/quickstart.md)
- [Deployment Guide](architecture/deployment.md)
