# Guide for Administrators

This guide is for people who own ezrules in production or pre-production environments.
It focuses on practical operations: setup, access control, health checks, and maintenance.

---

## Admin Responsibilities

- Initialize and maintain the database
- Manage users, roles, and permissions
- Monitor API and worker health
- Maintain backups and recovery process
- Review audit history and access controls

---

## Initial Setup

```bash
uv run ezrules init-db
uv run ezrules init-permissions
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

Recommended local infrastructure:

```bash
docker compose up -d
```

---

## User and Role Management

Default roles:

- `admin`
- `rule_editor`
- `readonly`

Core APIs:

- `GET /api/v2/users`
- `POST /api/v2/users`
- `PUT /api/v2/users/{user_id}`
- `DELETE /api/v2/users/{user_id}`
- `GET /api/v2/roles`
- `PUT /api/v2/roles/{role_id}/permissions`

OpenAPI docs: `http://localhost:8888/docs`

---

## Permission Model

ezrules currently defines **27** permission actions, grouped across:

- rules
- outcomes
- lists
- labels
- audit
- users
- roles/permission management

Permissions are stored in:

- `actions`
- `role_actions`

---

## Health and Operations

API checks:

```bash
curl http://localhost:8888/ping
curl http://localhost:8888/docs
```

Backtesting worker:

- tasks are processed by Celery
- if worker is down, backtests remain `PENDING`

Run worker manually (macOS-safe):

```bash
uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
```

---

## Audit and History

Audit/history endpoints:

- `GET /api/v2/audit`
- `GET /api/v2/audit/rules`
- `GET /api/v2/audit/config`
- `GET /api/v2/audit/user-lists`
- `GET /api/v2/audit/outcomes`
- `GET /api/v2/audit/labels`

Related tables:

- `rules_history`
- `rule_engine_config_history`
- `user_list_history`
- `outcome_history`
- `label_history`

---

## Backups

Example PostgreSQL backup:

```bash
pg_dump -h localhost -U postgres ezrules | gzip > backup_$(date +%Y%m%d).sql.gz
```

Restore:

```bash
gunzip -c backup_20250109.sql.gz | psql -h localhost -U postgres ezrules
```

---

## Security Checklist

- Set strong `EZRULES_APP_SECRET`
- Restrict network access to Postgres/Redis
- Use HTTPS at reverse proxy/load balancer
- Use least-privilege roles for non-admin users
- Review audit history regularly

---

## Next Steps

- **[Configuration Guide](../getting-started/configuration.md)** - Env and runtime config
- **[Architecture Overview](../architecture/overview.md)** - System internals
- **[Deployment Guide](../architecture/deployment.md)** - Local deployment flow
