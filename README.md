# ezrules

Open-source transaction monitoring engine for business rules.

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

## ✨ Features

- **Rule Engine**: Flexible Python-based rule execution with custom logic support
- **Management Interface**: Modern web UI for creating and managing rules
- **Enterprise Security**: Granular role-based access control with 27 permission types
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
- **API Service**: FastAPI-based API with JWT authentication, including real-time rule evaluation at `/api/v2/evaluate` (default port 8888)
- **Web Frontend**: Modern UI for rule management, analytics, and administration
- **Database Layer**: PostgreSQL storage for rules, events, and execution logs

### Data Flow

1. Events are submitted to the API service at `/api/v2/evaluate`
2. Rules are executed against event data
3. Outcomes are aggregated and stored
4. Results are available via API and web interface

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **PostgreSQL** — used for rule storage, audit logs, and Celery result backend
- **Redis** — used as the Celery message broker for backtesting tasks
- **Docker & Docker Compose** (recommended) — to run PostgreSQL, Redis, and the Celery worker with a single command

#### Start infrastructure with Docker Compose (recommended)

```bash
docker compose up -d
```

This starts three services in the background:
- **PostgreSQL** on port 5432 — database (data persisted in a Docker volume)
- **Redis** on port 6379 — Celery message broker
- **Celery worker** — processes backtest tasks (built from the project `Dockerfile`)

The worker waits for PostgreSQL and Redis to be healthy before starting.

To stop:

```bash
docker compose down        # stop containers, keep data
docker compose down -v     # stop containers and delete data
```

After `docker compose up -d`, you only need to run the API locally:
```bash
uv run ezrules api --port 8888
```

#### Or install services manually

<details>
<summary>Manual installation instructions</summary>

**Redis:**
```bash
# macOS
brew install redis && brew services start redis

# Ubuntu/Debian
sudo apt install redis-server && sudo systemctl start redis
```

**PostgreSQL:** Install via your system package manager or use the standalone Docker script in `scripts/run_postgres_locally.sh`.

</details>

Redis must be running on `localhost:6379` (default). To use a different URL, set the `EZRULES_CELERY_BROKER_URL` environment variable (e.g. `redis://myhost:6380/0`).

### Installation

```bash
# Clone the repository
git clone https://github.com/sofeikov/ezrules.git
cd ezrules

# Install dependencies
uv sync
```

### Database Setup

```bash
# Initialize the database
uv run ezrules init-db

# Initialize database with automatic deletion of existing database (non-interactive)
uv run ezrules init-db --auto-delete

# Set up permissions and default roles
uv run ezrules init-permissions

# Add a user
uv run ezrules add-user --user-email admin@example.com --password admin
```

The `init-db` command automatically handles database creation and provides options for managing existing databases:

- **Interactive mode** (default): Prompts if you want to delete and recreate existing databases
- **Auto-delete mode** (`--auto-delete`): Automatically deletes existing databases without prompting
- **Smart creation**: Only creates the database if it doesn't already exist

### Start Services

```bash
# Start the API service (FastAPI - includes rule evaluation and frontend API)
uv run ezrules api --port 8888
# With auto-reload for development:
uv run ezrules api --port 8888 --reload
```

#### Celery Worker (required for backtesting)

The backtesting feature runs rule comparisons asynchronously via Celery. A Celery worker must be running for backtest tasks to execute.

If you're using `docker compose up -d`, the worker is **already running** — no extra steps needed.

To run the worker manually instead (e.g. for debugging):

```bash
# On macOS, use --pool=solo to avoid fork-related crashes (SIGSEGV)
uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo

# On Linux, the default prefork pool works fine:
uv run celery -A ezrules.backend.tasks worker -l INFO
```

A VS Code launch configuration named **"Celery Worker"** is also available in `.vscode/launch.json` for debugging the worker with breakpoints.

**Architecture notes:**
- **Broker** (Redis): Delivers task messages from the API to the worker
- **Result backend** (PostgreSQL): Stores task results in the same database as the application, using the `EZRULES_DB_ENDPOINT` connection string
- Without a running worker, backtest requests will remain in `PENDING` state indefinitely

### Web Frontend

ezrules includes a web frontend that communicates with the FastAPI backend.

#### Features

The frontend provides:
- **Rule List View**: Browse all rules with a modern, responsive interface
- **Rule Detail View**: View comprehensive rule details including:
  - Rule ID, description, and logic
  - Created date and version history
  - Test functionality with dynamic JSON input
  - Real-time rule testing with sample data
  - Revision history browsing with read-only historical revision views
- **Labels Management**: Full CRUD for transaction labels — list, create, and delete labels (with confirmation), plus a link to bulk CSV upload
- **Label Analytics**: View labeled transaction analytics — total labeled events metric card, per-label time-series charts with Chart.js, and a time range selector (1h, 6h, 12h, 24h, 30d)
- **Seamless Navigation**: Navigate between rule list, detail, labels, and analytics pages

#### Build Frontend (optional)

```bash
cd ezrules/frontend
npm install
npm run build
```

Build output will be generated in `ezrules/frontend/dist/`.

### Generate Test Data

```bash
# Create sample rules and events for testing
uv run ezrules generate-random-data --n-rules 10 --n-events 100

# Generate events with realistic fraud labeling
uv run ezrules generate-random-data --n-events 100 --label-ratio 0.3 --export-csv test_labels.csv
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
