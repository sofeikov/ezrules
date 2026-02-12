# Configuration

ezrules uses environment variables for configuration. This guide covers all available options and best practices.

---

## Environment Variables

### Required Configuration

#### `EZRULES_DB_ENDPOINT`

Database connection string for PostgreSQL.

**Format:**
```
postgresql://username:password@host:port/database
```

**Example:**
```bash
export EZRULES_DB_ENDPOINT="postgresql://postgres:mypassword@localhost:5432/ezrules"
```

**Testing Database:**
```bash
export EZRULES_DB_ENDPOINT="postgresql://postgres:root@localhost:5432/tests"
```

---

### Core Configuration

#### `EZRULES_APP_SECRET`

Secret key used for security features (including JWT token signing).

**Default:** No code default (must be provided)

**Example:**
```bash
export EZRULES_APP_SECRET="your-secret-key-here-change-in-production"
```

!!! warning "Production Security"
    Always set a strong, unique secret key in production environments. Never commit secrets to version control.

#### `EZRULES_ORG_ID`

Organization ID for multi-tenant deployments.

**Default:** No code default (must be provided)

**Example:**
```bash
export EZRULES_ORG_ID="5"
```

### Optional Configuration

#### `EZRULES_TESTING`

Enable testing mode with additional debugging features.

**Default:** `false`

**Example:**
```bash
export EZRULES_TESTING="true"
```

#### `EZRULES_CELERY_BROKER_URL`

Broker URL for Celery backtesting tasks.

**Default:** `redis://localhost:6379`

**Example:**
```bash
export EZRULES_CELERY_BROKER_URL="redis://localhost:6379/0"
```

---

## Configuration Files

### Using settings.env (Recommended)

Create or update `settings.env` in your project root for local development:

```bash
# settings.env
EZRULES_DB_ENDPOINT=postgresql://postgres:password@localhost:5432/ezrules
EZRULES_APP_SECRET=dev-secret-key-change-me
EZRULES_ORG_ID=1
```

The application loads `settings.env` automatically. You can run:

```bash
uv run ezrules api
```

---

## Service Configuration

### API Service Options

The API service exposes REST endpoints and rule evaluation. It accepts these command-line arguments:

```bash
uv run ezrules api [OPTIONS]
```

**Options:**

- `--port PORT` - Server port (default: 8888)
- `--reload` - Enable auto-reload for development

**Example:**
```bash
uv run ezrules api --port 8888
```

!!! note "Removed Commands"
    The `ezrules manager` and `ezrules evaluator` CLI commands have been removed. The evaluation endpoint is available at `/api/v2/evaluate` on the main API service. Use `uv run ezrules api` for all services.

---

## Database Configuration

### Connection Pooling

For production deployments, configure connection pooling:

```python
# config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_recycle': 3600,
}
```

### SSL Connections

For secure database connections:

```bash
export EZRULES_DB_ENDPOINT="postgresql://user:pass@host:5432/db?sslmode=require"
```

**SSL Modes:**
- `disable` - No SSL
- `require` - Require SSL (default for cloud databases)
- `verify-ca` - Verify CA certificate
- `verify-full` - Verify certificate and hostname

---

## Deployment Configurations

### Development

```bash
# .env.development
EZRULES_DB_ENDPOINT=postgresql://postgres:dev@localhost:5432/ezrules_dev
EZRULES_APP_SECRET=dev-secret-not-for-production
EZRULES_TESTING=true
```

### Staging

```bash
# .env.staging
EZRULES_DB_ENDPOINT=postgresql://ezrules:password@staging-db:5432/ezrules
EZRULES_APP_SECRET=${STAGING_SECRET}
EZRULES_ORG_ID=1
```

### Production

```bash
# .env.production
EZRULES_DB_ENDPOINT=postgresql://ezrules:${DB_PASSWORD}@prod-db:5432/ezrules
EZRULES_APP_SECRET=${PRODUCTION_SECRET}
EZRULES_ORG_ID=1
```

!!! danger "Production Checklist"
    - Use strong, unique secrets
    - Enable SSL for database connections
    - Set `EZRULES_TESTING=false`
    - Use connection pooling
    - Configure proper logging
    - Set up monitoring and alerting

---

## Logging Configuration

The project relies on Python's standard logging module. Adjust handlers or levels inside your service wrappers (for example, by calling `logging.basicConfig`) before invoking `uv run ezrules ...`.

---

## Celery Configuration (Optional)

If using background workers:

- The Celery app lives in `ezrules/backend/tasks.py`.
- The broker is configurable via `EZRULES_CELERY_BROKER_URL` (default: `redis://localhost:6379`).
- The result backend uses the primary database URL (`EZRULES_DB_ENDPOINT`).

---

## Advanced Configuration

### Customisation Hooks

Additional runtime behaviours (rule paths, query limits, multi-tenancy) are not controlled via environment variables today. Extend the codebase where needed--for example, by adapting `RuleManagerFactory` or wrapping database sessions with your own configuration.

---

## Configuration Validation

Verify your configuration:

```bash
# Test database connectivity
psql "$EZRULES_DB_ENDPOINT" -c "SELECT 1;"

# View available CLI commands
uv run ezrules --help
```

---

## Docker Configuration

When using Docker, pass environment variables:

```yaml
# docker-compose.yml
version: '3.8'
services:
  ezrules-api:
    image: ezrules:latest
    environment:
      - EZRULES_DB_ENDPOINT=postgresql://postgres:password@db:5432/ezrules
      - EZRULES_APP_SECRET=${SECRET_KEY}
      - EZRULES_ORG_ID=1
    ports:
      - "8888:8888"
    command: ["uv", "run", "ezrules", "api", "--port", "8888"]

  db:
    image: postgres:16
    environment:
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=ezrules
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## Troubleshooting

### Configuration Not Loading

1. Check environment variables are exported:
   ```bash
   echo $EZRULES_DB_ENDPOINT
   ```

2. Verify .env file location and format

3. Ensure no conflicting configuration sources

### Database Connection Fails

1. Test connection manually:
   ```bash
   psql "postgresql://postgres:password@localhost:5432/ezrules"
   ```

2. Check firewall rules and network connectivity

3. Verify credentials and database exists

For more help, [file an issue](https://github.com/sofeikov/ezrules/issues).
