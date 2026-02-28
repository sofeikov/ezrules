# ezrules

Open-source transaction monitoring engine for business rules.

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

## ✨ Features

- **Rule Engine**: Flexible Python-based rule execution with custom logic support
- **Management Interface**: Modern web UI for creating and managing rules
- **Enterprise Security**: Granular role-based access control with 28 permission types; API key authentication for service-to-service integration
- **Transaction Labeling**: Comprehensive fraud analytics with API and bulk CSV upload capabilities
- **Analytics Dashboard**: Real-time transaction volume charts with configurable time ranges (1h, 6h, 12h, 24h, 30d)
- **Scalable Architecture**: Unified API service with integrated rule evaluation
- **Database Integration**: PostgreSQL backend with SQLAlchemy ORM and full audit history
- **Audit Trail**: Change tracking for rules, user lists, outcomes, labels, and field type configurations, with per-change user attribution
- **Field Type Management**: Auto-discovers JSON field types from live traffic and test payloads; configurable type casting (integer, float, string, boolean, datetime) applied before rule evaluation so comparisons behave correctly regardless of how values arrive in JSON
- **Shadow Deployment**: Deploy rules to a shadow environment that observes live traffic without affecting production outcomes; promote validated shadows to production in one step
- **Backtesting**: Test rule changes against historical data before deployment
- **CLI Tools**: Command-line interface for database management and realistic test data generation

## 🏗️ Architecture

ezrules consists of several core components:

- **Rule Engine**: Evaluates events against defined rules and aggregates outcomes
- **API Service**: FastAPI-based API with JWT authentication, including real-time rule evaluation at `/api/v2/evaluate` (default port 8888); evaluate endpoint requires an `X-API-Key` header or Bearer token
- **Web Frontend**: Modern UI for rule management, analytics, and administration
- **Database Layer**: PostgreSQL storage for rules, events, and execution logs

### Data Flow

1. Events are submitted to the API service at `/api/v2/evaluate`
2. Rules are executed against event data
3. Outcomes are aggregated and stored
4. Results are available via API and web interface

## 🚀 Quick Start

### Prerequisites

- **Docker & Docker Compose** — the only hard requirement for the full-stack setups below
- **Python 3.12+ and `uv`** — only needed if you are contributing or running services locally outside Docker

---

### Option A — Demo (exploring the product)

One command. No configuration. Pre-loaded with sample rules and events.

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
docker compose -f docker-compose.demo.yml up --build
```

Once all containers are healthy:

| Service | URL |
|---|---|
| Web UI | http://localhost:4200 |
| API | http://localhost:8888 |

Login: `admin@example.com` / `admin`

To stop and wipe all data:

```bash
docker compose -f docker-compose.demo.yml down -v
```

---

### Option B — Production (real data)

Full stack with an empty database. Credentials come from a `.env` file you control.

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
cp .env.example .env          # edit with your own secret and admin credentials
docker compose -f docker-compose.prod.yml up --build
```

| Service | URL |
|---|---|
| Web UI | http://localhost:4200 |
| API | http://localhost:8888 |

Login with the email/password you set in `.env`.

To stop (data is preserved in a Docker volume):

```bash
docker compose -f docker-compose.prod.yml down
```

---

### Option C — Development (contributing to the project)

Runs only the infrastructure (PostgreSQL, Redis, Celery worker) via Docker. The API and frontend run locally for fast iteration.

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules

# Start infrastructure
docker compose up -d

# Install Python dependencies
uv sync

# Configure settings
cat > settings.env <<EOF
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules
EZRULES_APP_SECRET=dev_secret
EZRULES_ORG_ID=1
EOF

# Initialise DB and create an admin user
uv run ezrules init-db
uv run ezrules add-user --user-email admin@example.com --password admin --admin

# Start the API
uv run ezrules api --port 8888

# In another terminal — start the Angular dev server
cd ezrules/frontend && npm install && npm start
```

Open http://localhost:4200.

To generate sample data for development:

```bash
uv run ezrules generate-random-data --n-rules 10 --n-events 100
```

## 🔐 Enterprise Security

ezrules includes a comprehensive role-based access control system designed for enterprise compliance requirements.

### Permission Types

The system supports 27 granular permission types:

**Rule Management:**
- `create_rule` - Create new business rules
- `modify_rule` - Edit existing rules
- `delete_rule` - Delete rules
- `view_rules` - View rules and rule history

**Outcome Management:**
- `create_outcome` - Add new outcome types
- `modify_outcome` - Edit outcome definitions
- `delete_outcome` - Remove outcome types
- `view_outcomes` - View outcome configurations

**List Management:**
- `create_list` - Create new user lists
- `modify_list` - Add/remove list entries
- `delete_list` - Delete entire lists
- `view_lists` - View user lists

**Label Management:**
- `create_label` - Create transaction labels
- `modify_label` - Modify transaction labels
- `delete_label` - Delete transaction labels
- `view_labels` - View transaction labels

**Audit Access:**
- `access_audit_trail` - View system audit logs and change history

**User Management:**
- `view_users` - View users
- `create_user` - Create users
- `modify_user` - Modify users
- `delete_user` - Delete users
- `manage_user_roles` - Assign/remove user roles

**Role & Permission Management:**
- `view_roles` - View roles
- `create_role` - Create roles
- `modify_role` - Modify roles
- `delete_role` - Delete roles
- `manage_permissions` - Manage role permissions

### Default Roles

Three pre-configured roles are available:

- **Admin**: Full system access with all permissions
- **Rule Editor**: Can create and modify rules, view outcomes and lists
- **Read-only**: View-only access to rules, outcomes, and lists

### Role Assignment

Users can be assigned to roles through the database or programmatically. The permission system supports:

- Multiple roles per user
- Organization-scoped data model (`o_id`) used by core entities
- Audit history for rules, user lists, outcomes, and labels

## 🏷️ Transaction Labeling & Analytics

ezrules includes comprehensive transaction labeling capabilities for fraud detection analytics and model validation.

### Labeling Methods

**Single Event API**: Programmatically mark individual transactions
```bash
curl -X POST http://localhost:8888/api/v2/labels/mark-event \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"event_id": "txn_123", "label_name": "FRAUD"}'
```

**Bulk CSV Upload**: Upload CSV files through the web interface for batch labeling (no header row)
```csv
txn_456,NORMAL
txn_789,CHARGEBACK
```

### Label Analytics Dashboard

Access comprehensive analytics for labeled transactions via the web interface:

**Key Metrics:**
- **Total Labeled Events**: Track overall labeling coverage
- **Labels Over Time**: Individual time-series charts for each label type showing temporal trends

**Time Range Options**: View analytics over 1h, 6h, 12h, 24h, or 30d periods

**API Endpoints:**
- `/api/v2/analytics/labels-summary` - Summary statistics (total labeled events count)
- `/api/v2/analytics/labels-distribution` - Distribution of individual labels by time period

### Test Data Generation

Generate realistic test data with fraud patterns:

```bash
# Generate 200 events, label 40% with realistic patterns, export to CSV
uv run ezrules generate-random-data --n-events 200 --label-ratio 0.4 --export-csv fraud_test.csv

# Export existing events to CSV for testing uploads
uv run ezrules export-test-csv --n-events 50 --unlabeled-only --output-file test_upload.csv
```

### Built-in Labels

- **FRAUD**: Suspicious or confirmed fraudulent transactions
- **CHARGEBACK**: Disputed transactions resulting in chargebacks
- **NORMAL**: Legitimate transactions

### Analytics Benefits

- **False Positive Analysis**: Measure how often legitimate transactions are flagged
- **False Negative Analysis**: Identify missed fraud cases for rule improvement
- **Model Validation**: Test machine learning models against known outcomes
- **Performance Metrics**: Track rule effectiveness over time
- **Temporal Analysis**: Understand fraud patterns and trends over configurable time periods

## 💼 Use Cases

- **Financial Transaction Monitoring**: Real-time fraud detection and compliance checking
- **Enterprise Compliance**: Role-based access control with audit trails for regulatory requirements
- **Business Rule Automation**: Automated decision making based on configurable business logic
- **Event-Driven Processing**: Rule-based responses to system events and data changes
- **Fraud Analytics**: Comprehensive transaction labeling for performance analysis and model improvement

## 📖 Documentation

### Building Documentation

The project uses MkDocs for documentation generation:

```bash
# Build documentation
uv run mkdocs build

# Serve documentation locally with live reload
uv run mkdocs serve
# Then open http://127.0.0.1:8000/ in your browser

# Build and serve in one command
uv run mkdocs serve
```

The documentation is also available online at [ReadTheDocs](https://ezrules.readthedocs.io/).

## 🛠️ Development

### Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, Celery
- **Frontend**: Angular, Tailwind CSS, Chart.js
- **Database**: PostgreSQL
- **Task Queue**: Celery with Redis broker and PostgreSQL result backend (for backtesting)
- **Authentication**: JWT tokens (API v2)

### Code Quality

```bash
# Run linting and type checking
uv run poe check

# Run tests
uv run pytest
```

### Testing

#### Backend Tests

```bash
# Run tests with coverage
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests

# Run CLI tests
./test_cli.sh

# Code quality checks (ruff format, type checking, linting)
uv run poe check

# Generate test data
uv run ezrules generate-random-data

# Clean up test data
uv run ezrules delete-test-data
```

#### Frontend Tests

The Angular frontend includes comprehensive end-to-end tests using Playwright.

**Prerequisites:**
- API service running on port 8888
- Angular dev server running (port 4200)
- Playwright browsers installed (first time only): `npx playwright install chromium`
```bash
cd ezrules/frontend
npm run test:e2e
```

## 📄 License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.
