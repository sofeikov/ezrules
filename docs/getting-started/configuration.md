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

Secret key for Flask session management and security features.

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
uv run ezrules manager
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

### Manager Service Options

The web interface service accepts these command-line arguments:

```bash
uv run ezrules manager [OPTIONS]
```

**Options:**

- `--port PORT` - Server port (default: 8888)
- `--host HOST` - Bind address (default: 0.0.0.0)
- `--debug` - Enable debug mode (development only)

**Example:**
```bash
uv run ezrules manager --port 8080 --host 127.0.0.1
```

### Evaluator Service Options

The API service for rule evaluation:

```bash
uv run ezrules evaluator [OPTIONS]
```

**Options:**

- `--port PORT` - Server port (default: 9999)
- `--host HOST` - Bind address (default: 0.0.0.0)
- `--workers N` - Number of worker processes (default: 4)

**Example:**
```bash
uv run ezrules evaluator --port 9000 --workers 8
```

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
    - ✅ Use strong, unique secrets
    - ✅ Enable SSL for database connections
    - ✅ Set `EZRULES_TESTING=false`
    - ✅ Use connection pooling
    - ✅ Configure proper logging
    - ✅ Set up monitoring and alerting

---

## Logging Configuration

ezrules uses Python's built-in logging. Configure via environment:

```bash
# Set log level
export EZRULES_LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Log to file
export EZRULES_LOG_FILE="/var/log/ezrules/app.log"
```

---

## Celery Configuration (Optional)

If using background workers:

```bash
# Redis broker
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"

# Or PostgreSQL broker
export CELERY_BROKER_URL="postgresql://postgres:password@localhost:5432/ezrules"
```

---

## Advanced Configuration

### Custom Rule Paths

Add custom rule directories:

```bash
export EZRULES_RULE_PATHS="/app/custom_rules:/opt/rules"
```

### Performance Tuning

```bash
# Database query timeout (seconds)
export EZRULES_QUERY_TIMEOUT="30"

# Max events per batch
export EZRULES_BATCH_SIZE="1000"

# Rule execution timeout (seconds)
export EZRULES_RULE_TIMEOUT="5"
```

### Multi-Tenancy

For multi-organization deployments:

```bash
# Enable tenant isolation
export EZRULES_MULTI_TENANT="true"

# Default organization
export EZRULES_DEFAULT_ORG_ID="1"
```

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
  ezrules-manager:
    image: ezrules:latest
    environment:
      - EZRULES_DB_ENDPOINT=postgresql://postgres:password@db:5432/ezrules
      - EZRULES_APP_SECRET=${SECRET_KEY}
    ports:
      - "8888:8888"
    command: manager --port 8888

  ezrules-evaluator:
    image: ezrules:latest
    environment:
      - EZRULES_DB_ENDPOINT=postgresql://postgres:password@db:5432/ezrules
    ports:
      - "9999:9999"
    command: evaluator --port 9999 --workers 4

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
