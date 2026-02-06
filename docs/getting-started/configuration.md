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

### Optional Configuration

#### `EZRULES_APP_SECRET`

Secret key for session management and security features.

**Default:** Auto-generated random string

**Example:**
```bash
export EZRULES_APP_SECRET="your-secret-key-here-change-in-production"
```

!!! warning "Production Security"
    Always set a strong, unique secret key in production environments. Never commit secrets to version control.

#### `EZRULES_ORG_ID`

Organization ID for multi-tenant deployments.

**Default:** `1`

**Example:**
```bash
export EZRULES_ORG_ID="5"
```

#### `EZRULES_TESTING`

Enable testing mode with additional debugging features.

**Default:** `false`

**Example:**
```bash
export EZRULES_TESTING="true"
```

---

## Configuration Files

### Using .env Files

Create a `.env` file in your project root for local development:

```bash
# .env file
EZRULES_DB_ENDPOINT=postgresql://postgres:password@localhost:5432/ezrules
EZRULES_APP_SECRET=dev-secret-key-change-me
EZRULES_ORG_ID=1
```

Load the file before running commands:

```bash
source .env
uv run ezrules api
```

Or use a tool like `direnv` to auto-load:

```bash
# Install direnv
brew install direnv  # macOS

# Add to .envrc
echo "source .env" > .envrc
direnv allow
```

---

## Service Configuration

### API Service Options

The API service provides both the web interface and the evaluation API. It accepts these command-line arguments:

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

!!! note "Deprecated: Evaluator Command"
    The standalone `uv run ezrules evaluator` command is deprecated. The evaluation endpoint is now available at `/api/v2/evaluate` on the main API service. Use `uv run ezrules api` instead.

### Manager Service Options (Legacy)

The legacy Flask manager web interface:

```bash
uv run ezrules manager [OPTIONS]
```

**Options:**

- `--port PORT` - Server port (default: 8888)

**Example:**
```bash
uv run ezrules manager --port 8080
```

!!! note "Additional Configuration"
    Both services use gunicorn with 1 worker and 4 threads by default. To modify these settings, you'll need to run gunicorn directly instead of using the CLI commands.

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
- The broker is currently fixed to `redis://localhost:6379` and the result backend uses the primary database URL.
- Adjust those settings in code before deploying to production.

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
    ports:
      - "8888:8888"
    command: api --port 8888

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
