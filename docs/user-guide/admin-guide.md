# Guide for Administrators

This guide is for operators responsible for uptime, access control, and recovery.

## Scope

Use this page for:

- initial environment setup
- user/role administration
- health checks and incident response
- backup and restore operations

Use [Deployment Guide](../architecture/deployment.md) for local deployment flow details.

---

## Assumptions

- You can run CLI commands on the service host
- You can access PostgreSQL and Redis
- You have admin credentials for ezrules

---

## Runbook: Initial Setup

### Action

```bash
uv run ezrules init-db
uv run ezrules init-permissions
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

### Verify

- `http://localhost:8888/ping` responds
- Admin user can log in to the UI
- **Security** and **Settings** pages are visible in sidebar

### Rollback / Recovery

- If initialization was run with wrong DB settings, fix `EZRULES_DB_ENDPOINT` and rerun setup commands
- If admin login fails, recreate user with `add-user`

---

## Runbook: User and Role Management

### UI-first workflow

1. Open **Security** for user management
2. Open **Settings** for role/permission management
3. Apply least-privilege role assignments

### API endpoints

- `GET /api/v2/users`
- `POST /api/v2/users`
- `PUT /api/v2/users/{user_id}`
- `DELETE /api/v2/users/{user_id}`
- `GET /api/v2/roles`
- `PUT /api/v2/roles/{role_id}/permissions`

### Verify

- Modified user/role appears in UI
- Target user can perform expected actions and is blocked from restricted actions

---

## Runbook: Health Checks

### Action

```bash
curl http://localhost:8888/ping
curl http://localhost:8888/docs
docker compose ps
```

### Verify

- API responds successfully
- OpenAPI docs load
- Required infra services are `Up` (Postgres, Redis, worker if used)

### If Backtests Stay `PENDING`

Likely cause: Celery worker is down.

```bash
uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
```

Then re-check task status via `/api/v2/backtesting/task/{task_id}`.

---

## Runbook: Audit and Change Tracking

Use audit endpoints during incident review or compliance checks:

- `GET /api/v2/audit`
- `GET /api/v2/audit/rules`
- `GET /api/v2/audit/config`
- `GET /api/v2/audit/user-lists`
- `GET /api/v2/audit/outcomes`
- `GET /api/v2/audit/labels`

Operational tip:

- Capture `changed_by` values and timestamps when preparing incident timelines

---

## Runbook: Backup and Restore

### Backup

```bash
pg_dump -h localhost -U postgres ezrules | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore

```bash
gunzip -c backup_20250109.sql.gz | psql -h localhost -U postgres ezrules
```

### Verify

- API starts cleanly after restore
- Recent rules, outcomes, and users are present
- Basic evaluate request succeeds

### Safety Notes

- Test restores in non-production before production use
- Keep backup retention and encryption policies outside app repo

---

## Security Checklist

- Set strong `EZRULES_APP_SECRET`
- Restrict network access to Postgres and Redis
- Use HTTPS at reverse proxy or load balancer
- Use least-privilege roles for non-admin users
- Review audit history on a fixed cadence

---

## Next Steps

- **[Configuration Guide](../getting-started/configuration.md)** - environment and runtime config
- **[Architecture Overview](../architecture/overview.md)** - system boundaries and design decisions
- **[Troubleshooting](../troubleshooting.md)** - symptom-based diagnostics
