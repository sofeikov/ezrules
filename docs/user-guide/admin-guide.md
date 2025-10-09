# Guide for Administrators

This guide is for system administrators who manage ezrules installations, users, permissions, and infrastructure.

---

## Your Responsibilities

As an administrator, you'll:
- Install and configure ezrules
- Manage users and permissions
- Monitor system health and performance
- Handle backups and disaster recovery
- Scale the system as needed
- Maintain security and compliance

---

## User Management

### Adding Users

Via command line:

```bash
uv run ezrules add-user --user-email analyst@company.com --password temp123
```

!!! warning "Initial Passwords"
    Always use temporary passwords and require users to change them on first login.

### User Roles

ezrules includes three default roles:

#### Admin
Full system access including:
- All rule, outcome, and list permissions
- User management (via CLI)
- Audit trail access
- System configuration

#### Rule Editor
Can create and modify rules:
- Create, modify, delete rules
- View outcomes and lists
- Cannot access audit trail
- Cannot manage users

#### Read-only
View-only access:
- View rules, outcomes, lists
- Cannot make changes
- Good for reporting or training accounts

### Assigning Roles

Roles are assigned via database or programmatically:

```python
from ezrules.models import User, Role
from ezrules.core.database import Session

session = Session()

# Get user and role
user = session.query(User).filter_by(email='analyst@company.com').first()
editor_role = session.query(Role).filter_by(name='Rule Editor').first()

# Assign role
user.roles.append(editor_role)
session.commit()
```

---

## Permission System

### Available Permissions

ezrules has 13 granular permission types:

**Rule Management:**
- `create_rule` - Create new business rules
- `modify_rule` - Edit existing rules
- `delete_rule` - Delete rules
- `view_rules` - View rules and history

**Outcome Management:**
- `create_outcome` - Add outcome types
- `modify_outcome` - Edit outcomes
- `delete_outcome` - Remove outcomes
- `view_outcomes` - View outcome configurations

**List Management:**
- `create_list` - Create user lists (blocklists, allowlists)
- `modify_list` - Add/remove list entries
- `delete_list` - Delete entire lists
- `view_lists` - View user lists

**Audit:**
- `access_audit_trail` - View system audit logs

### Custom Roles

Create custom roles for your organization:

```python
from ezrules.models import Role, Permission

# Create role
custom_role = Role(
    name='Compliance Reviewer',
    description='Can view everything but not modify'
)

# Add permissions
permissions = ['view_rules', 'view_outcomes', 'view_lists', 'access_audit_trail']
for perm_name in permissions:
    perm = session.query(Permission).filter_by(name=perm_name).first()
    custom_role.permissions.append(perm)

session.add(custom_role)
session.commit()
```

### Checking Permissions

Users can have multiple roles. Permissions are aggregated:

```python
user.has_permission('create_rule')  # Returns True/False
```

---

## Database Management

### Initialization

Initialize a fresh database:

```bash
# Interactive mode (prompts for confirmation)
uv run ezrules init-db

# Non-interactive (auto-deletes existing)
uv run ezrules init-db --auto-delete
```

### Permissions Setup

Initialize RBAC system:

```bash
uv run ezrules init-permissions
```

This creates:
- All 13 permission types
- 3 default roles (Admin, Rule Editor, Read-only)
- Role-permission mappings

### Backups

**PostgreSQL Backup:**

```bash
# Full backup
pg_dump -h localhost -U postgres ezrules > backup_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -h localhost -U postgres ezrules | gzip > backup_$(date +%Y%m%d).sql.gz

# Schema only
pg_dump -h localhost -U postgres --schema-only ezrules > schema_backup.sql
```

**Automated Backups:**

```bash
#!/bin/bash
# backup.sh - Run daily via cron

BACKUP_DIR="/backups/ezrules"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
pg_dump -h localhost -U postgres ezrules | gzip > "$BACKUP_DIR/ezrules_$DATE.sql.gz"

# Keep last 30 days
find $BACKUP_DIR -name "ezrules_*.sql.gz" -mtime +30 -delete
```

Add to crontab:
```bash
# Run daily at 2 AM
0 2 * * * /path/to/backup.sh
```

### Restore

```bash
# From uncompressed backup
psql -h localhost -U postgres ezrules < backup_20250109.sql

# From compressed backup
gunzip -c backup_20250109.sql.gz | psql -h localhost -U postgres ezrules
```

---

## System Monitoring

### Health Checks

**Manager Service:**
```bash
curl http://localhost:8888/ping
# Should return 200 OK
```

**Evaluator Service:**
```bash
curl http://localhost:9999/health
# Should return {"status": "healthy"}
```

**Database:**
```bash
psql -h localhost -U postgres ezrules -c "SELECT 1;"
```

### Performance Monitoring

**Database Connection Pool:**

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'ezrules';

-- Long-running queries
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 minutes';
```

**Rule Execution Times:**

Query the audit logs to find slow rules:

```sql
SELECT rule_id, AVG(execution_time_ms) as avg_time
FROM rule_executions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY rule_id
ORDER BY avg_time DESC
LIMIT 10;
```

### Logging

**Application Logs:**

Set log level via environment:
```bash
export EZRULES_LOG_LEVEL="INFO"
```

**Centralized Logging:**

Configure log forwarding to your logging system:

```python
# config.py
import logging
from logging.handlers import SysLogHandler

handler = SysLogHandler(address='/dev/log')
logging.getLogger('ezrules').addHandler(handler)
```

---

## Scaling

### Horizontal Scaling

Run multiple evaluator instances behind a load balancer:

```yaml
# docker-compose.yml
services:
  evaluator-1:
    image: ezrules:latest
    command: evaluator --port 9999

  evaluator-2:
    image: ezrules:latest
    command: evaluator --port 9999

  evaluator-3:
    image: ezrules:latest
    command: evaluator --port 9999

  loadbalancer:
    image: nginx:latest
    ports:
      - "9999:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

**nginx.conf:**
```nginx
upstream evaluators {
    server evaluator-1:9999;
    server evaluator-2:9999;
    server evaluator-3:9999;
}

server {
    listen 80;
    location / {
        proxy_pass http://evaluators;
    }
}
```

### Database Optimization

**Add Indexes:**

```sql
-- Index commonly queried fields
CREATE INDEX idx_events_timestamp ON events(created_at);
CREATE INDEX idx_events_user_id ON events(user_id);
CREATE INDEX idx_outcomes_rule_id ON outcomes(rule_id);
CREATE INDEX idx_labels_event_id ON event_labels(event_id);
```

**Connection Pooling:**

Configure in your database connection:

```bash
export EZRULES_DB_ENDPOINT="postgresql://user:pass@host:5432/ezrules?pool_size=20&max_overflow=10"
```

### Caching

Implement Redis caching for frequently accessed data:

```python
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

# Cache user lists
def get_blocklist():
    cached = cache.get('blocklist')
    if cached:
        return json.loads(cached)

    blocklist = query_database()
    cache.setex('blocklist', 3600, json.dumps(blocklist))
    return blocklist
```

---

## Security

### Access Control

**Firewall Rules:**

Only expose necessary ports:

```bash
# Allow only internal network to manager
ufw allow from 10.0.0.0/8 to any port 8888

# Allow application servers to evaluator
ufw allow from 192.168.1.0/24 to any port 9999
```

**SSL/TLS:**

Use a reverse proxy with SSL:

```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8888;
    }
}
```

### Secret Management

**Never commit secrets to version control!**

Use a secrets manager:

```bash
# AWS Secrets Manager
export EZRULES_DB_ENDPOINT=$(aws secretsmanager get-secret-value \
  --secret-id prod/ezrules/db --query SecretString --output text)

# HashiCorp Vault
export EZRULES_APP_SECRET=$(vault kv get -field=secret secret/ezrules/app)
```

### Audit Trail

All permission-related actions are logged. View audit trail:

```python
from ezrules.models import AuditLog

# Query recent changes
logs = session.query(AuditLog)\
    .filter(AuditLog.created_at > datetime.now() - timedelta(days=7))\
    .order_by(AuditLog.created_at.desc())\
    .all()

for log in logs:
    print(f"{log.created_at}: {log.user.email} - {log.action}")
```

---

## Deployment

### Docker Deployment

**Dockerfile:**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN pip install uv
RUN uv sync

CMD ["uv", "run", "ezrules", "manager"]
```

**Build and Run:**

```bash
docker build -t ezrules:latest .

docker run -d \
  --name ezrules-manager \
  -e EZRULES_DB_ENDPOINT="postgresql://..." \
  -e EZRULES_APP_SECRET="..." \
  -p 8888:8888 \
  ezrules:latest
```

### Kubernetes Deployment

**deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ezrules-evaluator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ezrules-evaluator
  template:
    metadata:
      labels:
        app: ezrules-evaluator
    spec:
      containers:
      - name: evaluator
        image: ezrules:latest
        command: ["uv", "run", "ezrules", "evaluator"]
        env:
        - name: EZRULES_DB_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: ezrules-secrets
              key: db-endpoint
        ports:
        - containerPort: 9999
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

---

## Maintenance

### Cleanup Old Data

Archive old events to keep database performant:

```sql
-- Archive events older than 90 days
CREATE TABLE events_archive AS
SELECT * FROM events WHERE created_at < NOW() - INTERVAL '90 days';

DELETE FROM events WHERE created_at < NOW() - INTERVAL '90 days';

-- Vacuum to reclaim space
VACUUM FULL events;
```

### Update ezrules

```bash
# Pull latest code
git pull origin main

# Update dependencies
uv sync

# Run migrations (if any)
uv run ezrules migrate

# Restart services
systemctl restart ezrules-manager
systemctl restart ezrules-evaluator
```

---

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   journalctl -u ezrules-manager -n 50
   ```

2. Verify configuration:
   ```bash
   uv run ezrules validate-config
   ```

3. Test database connectivity:
   ```bash
   psql "$EZRULES_DB_ENDPOINT"
   ```

### High Memory Usage

1. Check connection pool settings
2. Reduce number of workers
3. Implement caching
4. Archive old data

### Slow Performance

1. Add database indexes
2. Optimize rule code
3. Enable query caching
4. Scale horizontally

---

## Next Steps

- **[Configuration Guide](../getting-started/configuration.md)** - Advanced configuration options
- **[Architecture Overview](../architecture/overview.md)** - Understand system design
- **[Deployment Guide](../architecture/deployment.md)** - Production deployment patterns
