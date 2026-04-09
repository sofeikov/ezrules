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
uv run ezrules bootstrap-org --name your-org --admin-email admin@example.com --admin-password admin
```

### Verify

- `http://localhost:8888/ping` responds
- Admin user can log in to the UI
- **Security** and **Settings** pages are visible in sidebar
- SMTP settings are configured if you plan to use invitation/password reset emails:
  - `EZRULES_SMTP_HOST`, `EZRULES_SMTP_PORT`, `EZRULES_SMTP_USER`, `EZRULES_SMTP_PASSWORD`, `EZRULES_FROM_EMAIL`
  - `EZRULES_APP_BASE_URL` points to your frontend URL

### Rollback / Recovery

- If initialization was run with wrong DB settings, fix `EZRULES_DB_ENDPOINT` and rerun setup commands
- If admin login fails, rerun `bootstrap-org` for the same organisation or create another admin with `add-user --org-name`

---

## Runbook: User and Role Management

### UI-first workflow

1. Open **Security** for user management
2. Open **Settings** for role/permission management
3. Use **Invite User** for standard onboarding (email + optional role)
4. Apply least-privilege role assignments

### API endpoints

- `GET /api/v2/users`
- `POST /api/v2/users`
- `POST /api/v2/users/invite`
- `PUT /api/v2/users/{user_id}`
- `DELETE /api/v2/users/{user_id}`
- `GET /api/v2/roles`
- `PUT /api/v2/roles/{role_id}/permissions`
- `POST /api/v2/auth/accept-invite`
- `POST /api/v2/auth/forgot-password`
- `POST /api/v2/auth/reset-password`

### Verify

- Modified user/role appears in UI
- Target user can perform expected actions and is blocked from restricted actions
- Invitation emails contain links to `/accept-invite?token=...`
- Password reset emails contain links to `/reset-password?token=...`

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
- `GET /api/v2/audit/rules/{rule_id}`
- `GET /api/v2/audit/config`
- `GET /api/v2/audit/user-lists`
- `GET /api/v2/audit/outcomes`
- `GET /api/v2/audit/labels`
- `GET /api/v2/audit/users`
- `GET /api/v2/audit/roles`
- `GET /api/v2/audit/field-types`
- `GET /api/v2/audit/api-keys`

Operational tips:

- Capture `changed_by` values and timestamps when preparing incident timelines
- Watch for `rolled_back` rule actions when reconstructing emergency change timelines
- Watch for `reordered` rule actions when investigating decision-order changes in first-match mode
- Field type changes affect rule evaluation behavior; review `GET /api/v2/audit/field-types` when investigating unexpected rule outcomes
- Review `GET /api/v2/audit/api-keys` when tracing API key creation or revocation during an incident

If your organisation uses ordered main-rule execution, see [Ordered Rule Execution in ezrules](../blog/rule-ordering-first-match.md) for the operator-facing model, reorder workflow, and audit implications.

### Rule rollback in incident response

If a recently edited rule needs to be restored quickly:

1. Open the rule's **History** timeline in the UI.
2. Select the last known-good revision.
3. Trigger **Roll back to revision ...** to create a new draft version from that historical logic.
4. Re-test or shadow validate if time allows.
5. Promote the rollback draft if the rule needs to be active again in production.

Rollback preserves every prior revision. It is preferable to manual copy/paste because it records the recovery action explicitly in audit history.

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
