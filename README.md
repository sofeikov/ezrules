# ezrules

Open-source transaction monitoring engine for business rules.

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

## ✨ Features

- **Rule Engine**: Flexible Python-based rule execution with custom logic support
- **Management Interface**: Modern web UI for creating and managing rules
- **Enterprise Security**: Granular role-based access control with 32 permission types; API key authentication for service-to-service integration
- **Org-Aware Admin APIs**: Manager access tokens now carry organisation context, and core admin CRUD endpoints scope users, outcomes, user lists, field types, label assignment, and label analytics to the authenticated user's org
- **Transaction Labeling**: Comprehensive fraud analytics with API and bulk CSV upload capabilities
- **Analytics Dashboard**: Real-time transaction volume charts with configurable time ranges (1h, 6h, 12h, 24h, 30d)
- **Scalable Architecture**: Unified API service with integrated rule evaluation
- **Database Integration**: PostgreSQL backend with SQLAlchemy ORM and full audit history
- **Audit Trail**: Change tracking for rules, user lists, outcomes, labels, and field type configurations, with per-change user attribution and explicit rule lifecycle actions (`promoted`, `deactivated`, `rolled_back`, `deleted`)
- **Field Type Management**: Auto-discovers JSON field types from live traffic and test payloads; configurable type casting (integer, float, string, boolean, datetime) applied before rule evaluation so comparisons behave correctly regardless of how values arrive in JSON
- **Outcome Resolution Hierarchy**: Configure outcome severity order in Settings so conflicting rule hits resolve to one persisted winning outcome
- **Tested Events View**: Inspect the latest stored transactions, their final resolved outcomes, the raw event payload, every rule that fired for each event, see referenced payload fields highlighted inline inside the JSON with hover-based rule focus, jump straight from a trigger to the rule detail page, and refresh the list without reloading the whole app
- **Shadow Deployment**: Deploy rules to a shadow environment that observes live traffic without affecting production outcomes; promote validated shadows to production in one step
- **Rule Lifecycle Controls**: Rules now support `draft`, `active`, and `archived` states with explicit promotion and approver tracking (`effective_from`, `approved_by`, `approved_at`)
- **Permission-Aware Promotion UI**: Draft and shadow promotion controls are only shown to users who hold the `promote_rules` permission
- **Revision Rollback**: Restore logic and description from a historical rule revision into a new draft version directly from the history timeline, without deleting any audit history
- **Backtesting**: Test rule changes against historical data before deployment, with outcome counts plus label-aware precision/recall/F1 when labeled history exists
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
3. Outcomes are aggregated, resolved through the configured severity hierarchy, and stored
4. Results are available via API and web interface, including the dedicated **Tested Events** page for recent stored evaluations

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
| Mailpit UI (captured emails) | http://localhost:8025 |

Login: `admin@example.com` / `admin`

Re-running `docker compose -f docker-compose.demo.yml up --build` intentionally recreates the demo database from scratch so stale persisted schemas do not break the demo stack.

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
| Mailpit UI (default local SMTP sink) | http://localhost:8025 |

Login with the email/password you set in `.env`.

Re-running `docker compose -f docker-compose.prod.yml up --build` with an existing Docker volume keeps the data and applies pending database migrations before starting the services.

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
EZRULES_SMTP_HOST=localhost
EZRULES_SMTP_PORT=1025
EZRULES_FROM_EMAIL=no-reply@ezrules.local
EZRULES_APP_BASE_URL=http://localhost:4200
EOF

# Initialise DB and create an admin user
# init-db creates the database if missing, applies Alembic migrations, and seeds defaults
uv run ezrules init-db
uv run ezrules add-user --user-email admin@example.com --password admin --admin

# For existing databases, apply new migrations after pulling updates
uv run alembic upgrade head

# Start the API
uv run ezrules api --port 8888

# In another terminal — start the Angular dev server
cd ezrules/frontend && npm install && npm start
```

Open http://localhost:4200.
Open Mailpit at http://localhost:8025 to inspect invitation/password-reset emails in development.

To generate fraud-oriented demo data for development:

```bash
uv run ezrules generate-random-data --n-rules 10 --n-events 100
```

## 🔐 Enterprise Security

ezrules includes a comprehensive role-based access control system designed for enterprise compliance requirements.

### Permission Types

The system supports 32 granular permission types:

**Rule Management:**
- `create_rule` - Create new business rules
- `modify_rule` - Edit existing rules
- `promote_rules` - Promote draft or shadow rules to production
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
- **Rule Editor**: Can create and modify rules, deploy drafts to shadow, and view outcomes and lists; promotion remains a separate permission
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

**Bulk CSV Upload**: Upload CSV files from the **Labels** page for batch labeling with per-row success/error reporting (no header row)
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

### Rule Quality View

Use the **Rule Quality** page to evaluate underperforming rules from labeled events.

**What it shows:**
- **Best Rules**: Highest average F1 score
- **Needs Attention**: Lowest average F1 score
- **Pair Metrics Table**: Precision/recall/F1 for configured curated `outcome -> label` pairs with TP/FP/FN counts
- **Lookback control**: Query only recent labeled events to keep analytics responsive at scale
- **Snapshot timestamp**: Report is frozen "as of" a specific datetime for auditability

**API Endpoint:**
- `/api/v2/analytics/rule-quality?min_support=5&lookback_days=30` - Rule-level ranking plus pair-level metrics over a bounded window
- Async report flow:
  - `POST /api/v2/analytics/rule-quality/reports` (`force_refresh=false` returns existing snapshot only; `force_refresh=true` generates new)
  - `GET /api/v2/analytics/rule-quality/reports/{report_id}` (poll status/result)

Default lookback for Rule Quality can be configured in **Settings → General** and is stored as a runtime setting.
Curated rule-quality pairs are also managed in **Settings → General** and drive which pairs appear in reports.
`uv run ezrules reset-dev` now seeds a demo-ready curated pair set: `RELEASE -> CHARGEBACK`, `HOLD -> CHARGEBACK`, and `CANCEL -> FRAUD`.
It also writes a root-level `test_labels.csv` from the seeded labeled events so the Labels upload flow has a ready-made file after each reset.

### Bombardment with Fraud Labels

The bombardment script now sends the same demo-shaped event payloads used by `reset-dev`, so live traffic will hit the seeded showcase rules instead of bypassing them. It also supports low-rate fraud labeling directly after evaluation:

```bash
# Evaluate events with API key and label ~1% as FRAUD using bearer token
uv run python scripts/bombard_evaluator.py \
  --api-key <api_key> \
  --token <access_token> \
  --fraud-rate 0.01
```

This mirrors CSV-style labeling but works inline while generating evaluator traffic.

### Test Data Generation

Generate fraud-oriented demo data with correlated fields such as device age, 3DS, velocity, geography mismatch,
beneficiary age, prior chargeback history, plus a few showcase rules using branching, loops, and baseline calculations:

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
- API service running with email delivery enabled for invite/reset tests.
  Start API for e2e with `EZRULES_TESTING=false` (if `EZRULES_TESTING=true`, SMTP sends are skipped and email-flow tests fail).
- Angular dev server running
- Playwright browsers installed (first time only): `npx playwright install chromium`
```bash
# Example random high ports
API_PORT=38888
FRONTEND_PORT=44200

# Terminal 1: API (mail flows require TESTING=false)
EZRULES_TESTING=false \
EZRULES_SMTP_HOST=localhost \
EZRULES_SMTP_PORT=1025 \
EZRULES_FROM_EMAIL=no-reply@ezrules.local \
EZRULES_APP_BASE_URL=http://localhost:$FRONTEND_PORT \
uv run ezrules api --port $API_PORT

# Terminal 2: Frontend
cd ezrules/frontend
EZRULES_FRONTEND_API_URL=http://localhost:$API_PORT \
npm start -- --port $FRONTEND_PORT

# Terminal 3: E2E
cd ezrules/frontend
E2E_BASE_URL=http://localhost:$FRONTEND_PORT \
E2E_API_BASE_URL=http://localhost:$API_PORT \
npm run test:e2e
```

## 📄 License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.
