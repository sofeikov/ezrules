# Configuration

This page is organized for fast local setup first, then production hardening.

## Fast Path (Local Development)

Set these three variables first:

- `EZRULES_DB_ENDPOINT`
- `EZRULES_APP_SECRET`
- `EZRULES_ORG_ID`

If you use the Rules page "Evaluate" shortcut, set this too:

- `EZRULES_EVALUATOR_ENDPOINT`

Example `settings.env`:

```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:password@localhost:5432/ezrules
EZRULES_APP_SECRET=dev-secret-key-change-me
EZRULES_ORG_ID=1
EZRULES_EVALUATOR_ENDPOINT=http://localhost:8888/api/v2
```

Run the service:

--8<-- "snippets/start-api.md"

---

## Configuration Matrix

| Variable | Required | Default | Typical Value | Purpose |
|---|---|---|---|---|
| `EZRULES_DB_ENDPOINT` | Yes | None | `postgresql://user:pass@host:5432/db` | Primary database connection |
| `EZRULES_APP_SECRET` | Yes | None | strong random string | JWT/signing and security features |
| `EZRULES_ORG_ID` | Yes | None | `1` | Organization context |
| `EZRULES_EVALUATOR_ENDPOINT` | No | `localhost:9999` | `http://localhost:8888/api/v2` | Base URL used by Rules page "Evaluate" shortcut |
| `EZRULES_TESTING` | No | `false` | `true` in tests | Testing mode |
| `EZRULES_CELERY_BROKER_URL` | No | `redis://localhost:6379` | `redis://host:6379/0` | Celery broker for backtesting |

---

## Environment Loading

- Local development: place values in `settings.env` at repo root
- Process-level overrides: export variables in shell
- Containerized deployments: pass variables through container runtime

Example shell export:

```bash
export EZRULES_DB_ENDPOINT="postgresql://postgres:mypassword@localhost:5432/ezrules"
export EZRULES_APP_SECRET="your-secret-key"
export EZRULES_ORG_ID="1"
export EZRULES_EVALUATOR_ENDPOINT="http://localhost:8888/api/v2"
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
      - EZRULES_ORG_ID=1
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
