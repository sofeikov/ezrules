# Configuration

This page is organized for fast local setup first, then production hardening.

## Fast Path (Local Development)

Set these two variables first:

- `EZRULES_DB_ENDPOINT`
- `EZRULES_APP_SECRET`

If external clients or automation read the evaluator URL from `GET /api/v2/rules`, set this too:

- `EZRULES_EVALUATOR_ENDPOINT`

Example `settings.env`:

```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:password@localhost:5432/ezrules
EZRULES_APP_SECRET=dev-secret-key-change-me
EZRULES_EVALUATOR_ENDPOINT=http://localhost:8888/api/v2
EZRULES_APP_BASE_URL=http://localhost:4200
EZRULES_SMTP_HOST=smtp.example.com
EZRULES_SMTP_PORT=587
EZRULES_SMTP_USER=mailer-user
EZRULES_SMTP_PASSWORD=mailer-password
EZRULES_FROM_EMAIL=no-reply@example.com
EZRULES_RULE_QUALITY_LOOKBACK_DAYS=30
```

Run the service:

--8<-- "snippets/start-api.md"

Fresh database bootstrap does not create an organisation automatically. Create organisations explicitly with
`uv run ezrules bootstrap-org --name <org-name> --admin-email <email> --admin-password <password>`.
Manager requests and API-key evaluation derive org context from the authenticated user or API key, not from an environment variable.

---

## Configuration Matrix

| Variable | Required | Default | Typical Value | Purpose |
|---|---|---|---|---|
| `EZRULES_DB_ENDPOINT` | Yes | None | `postgresql://user:pass@host:5432/db` | Primary database connection |
| `EZRULES_APP_SECRET` | Yes | None | strong random string | JWT/signing and security features |
| `EZRULES_EVALUATOR_ENDPOINT` | No | `localhost:9999` | `http://localhost:8888/api/v2` | Evaluator base URL advertised in `GET /api/v2/rules` responses |
| `EZRULES_TESTING` | No | `false` | `true` in tests | Testing mode |
| `EZRULES_MAX_BODY_SIZE_KB` | No | `1024` | `2048` | Reject requests whose declared body size exceeds this limit |
| `EZRULES_CELERY_BROKER_URL` | No | `redis://localhost:6379` | `redis://host:6379/0` | Celery broker for backtesting |
| `EZRULES_SMTP_HOST` | No | None | `smtp.example.com` | SMTP host for invitation/password reset emails |
| `EZRULES_SMTP_PORT` | No | `587` | `587` | SMTP port |
| `EZRULES_SMTP_USER` | No | None | `mailer-user` | SMTP username |
| `EZRULES_SMTP_PASSWORD` | No | None | `mailer-password` | SMTP password |
| `EZRULES_FROM_EMAIL` | No | None | `no-reply@example.com` | Sender address for auth emails |
| `EZRULES_RULE_QUALITY_LOOKBACK_DAYS` | No | `30` | `30` | Fallback default lookback window (days) for rule-quality analytics |
| `EZRULES_RULE_QUALITY_REPORT_SYNC_FALLBACK` | No | `true` | `true` | If worker is unavailable, compute pending reports inline on status polling |
| `EZRULES_APP_BASE_URL` | No | `http://localhost:4200` | `https://app.company.com` | Base UI URL used to build invite/reset links |
| `EZRULES_INVITE_TOKEN_EXPIRY_HOURS` | No | `72` | `24` | Invitation token lifetime in hours |
| `EZRULES_PASSWORD_RESET_TOKEN_EXPIRY_HOURS` | No | `1` | `1` | Password reset token lifetime in hours |

---

## Environment Loading

- Local development: place values in `settings.env` at repo root
- Process-level overrides: export variables in shell
- Containerized deployments: pass variables through container runtime

Example shell export:

```bash
export EZRULES_DB_ENDPOINT="postgresql://postgres:mypassword@localhost:5432/ezrules"
export EZRULES_APP_SECRET="your-secret-key"
export EZRULES_EVALUATOR_ENDPOINT="http://localhost:8888/api/v2"
export EZRULES_APP_BASE_URL="http://localhost:4200"
export EZRULES_SMTP_HOST="smtp.example.com"
export EZRULES_SMTP_PORT="587"
export EZRULES_SMTP_USER="mailer-user"
export EZRULES_SMTP_PASSWORD="mailer-password"
export EZRULES_FROM_EMAIL="no-reply@example.com"
export EZRULES_RULE_QUALITY_LOOKBACK_DAYS="30"
export EZRULES_RULE_QUALITY_REPORT_SYNC_FALLBACK="true"
```

---

## API Service Runtime Options

```bash
uv run ezrules api [OPTIONS]
```

Supported options:

- `--port PORT` (default `8888`)
- `--reload` (development only)

!!! note "Command Naming"
    `ezrules manager` and `ezrules evaluator` were removed.
    Use `uv run ezrules api` for the active backend service.

---

## Production Hardening

### Secrets

- Use strong unique values for `EZRULES_APP_SECRET`
- Never commit real secrets

### Database Transport Security

```bash
export EZRULES_DB_ENDPOINT="postgresql://user:pass@host:5432/db?sslmode=require"
```

Common `sslmode` values:

- `disable`
- `require`
- `verify-ca`
- `verify-full`

### Connection Pooling

For high-load environments, tune SQLAlchemy engine options in your service wrapper or app config.

### Worker/Broker

If you use backtesting:

- ensure Redis is reachable via `EZRULES_CELERY_BROKER_URL`
- ensure Celery workers are running

---

## Validation Checklist

Use this checklist after any config change:

1. DB connectivity check:
   ```bash
   psql "$EZRULES_DB_ENDPOINT" -c "SELECT 1;"
   ```
2. API health check: `http://localhost:8888/ping`
3. OpenAPI availability: `http://localhost:8888/docs`
4. Auth check: login succeeds from UI or `POST /api/v2/auth/login`

---

## Docker Example

```yaml
services:
  ezrules-api:
    image: ezrules:latest
    environment:
      - EZRULES_DB_ENDPOINT=postgresql://postgres:password@db:5432/ezrules
      - EZRULES_APP_SECRET=${SECRET_KEY}
    command: ["uv", "run", "ezrules", "api", "--port", "8888"]
```

---

## Troubleshooting

Start with [Troubleshooting](../troubleshooting.md) for symptom-based diagnostics.

Common quick checks:

```bash
echo "$EZRULES_DB_ENDPOINT"
uv run ezrules --help
```
