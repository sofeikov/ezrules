# ezrules

Open-source transaction monitoring engine for business rules.

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

## ✨ Features

- **Rule Engine**: Flexible Python-based rule execution with custom logic support
- **Web Management Interface**: Flask-based UI for creating and managing rules
- **Enterprise Security**: Granular role-based access control with 13 permission types
- **Transaction Labeling**: Comprehensive fraud analytics with API and bulk CSV upload capabilities
- **Scalable Architecture**: Multi-service deployment with dedicated manager and evaluator services
- **Database Integration**: PostgreSQL backend with SQLAlchemy ORM and full audit history
- **Audit Trail**: Complete access control and change tracking for compliance
- **Backtesting**: Test rule changes against historical data before deployment
- **CLI Tools**: Command-line interface for database management and realistic test data generation
- **Frontend Dashboard**: Next.js-based user interface for rule monitoring and analytics

## 🏗️ Architecture

ezrules consists of several core components:

- **Rule Engine**: Evaluates events against defined rules and aggregates outcomes
- **Manager Service**: Web interface for rule management (default port 8888)
- **Evaluator Service**: API service for real-time rule evaluation (default port 9999)
- **Database Layer**: PostgreSQL storage for rules, events, and execution logs

### Data Flow

1. Events are submitted to the evaluator service
2. Rules are executed against event data
3. Outcomes are aggregated and stored
4. Results are available via API and web interface

## 🚀 Quick Start

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
# Start the manager service (web interface)
uv run ezrules manager --port 8888

# Start the evaluator service (API)
uv run ezrules evaluator --port 9999

# Run the Celery workers
uv run celery -A ezrules.backend.tasks worker -l INFO
```

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

The system supports 13 granular permission types:

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

**Audit Access:**
- `access_audit_trail` - View system audit logs and change history

### Default Roles

Three pre-configured roles are available:

- **Admin**: Full system access with all permissions
- **Rule Editor**: Can create and modify rules, view outcomes and lists
- **Read-only**: View-only access to rules, outcomes, and lists

### Role Assignment

Users can be assigned to roles through the database or programmatically. The permission system supports:

- Multiple roles per user
- Resource-level permissions (coming soon)
- Department isolation capabilities
- Complete audit trail of permission changes

## 🏷️ Transaction Labeling & Analytics

ezrules includes comprehensive transaction labeling capabilities for fraud detection analytics and model validation.

### Labeling Methods

**Single Event API**: Programmatically mark individual transactions
```bash
curl -X POST http://localhost:9999/mark-event \
  -H "Content-Type: application/json" \
  -d '{"event_id": "txn_123", "label_name": "FRAUD"}'
```

**Bulk CSV Upload**: Upload CSV files through the web interface for batch labeling
```csv
event_id,label_name
txn_456,NORMAL
txn_789,CHARGEBACK
```

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

## 💼 Use Cases

- **Financial Transaction Monitoring**: Real-time fraud detection and compliance checking
- **Enterprise Compliance**: Role-based access control with audit trails for regulatory requirements
- **Business Rule Automation**: Automated decision making based on configurable business logic
- **Event-Driven Processing**: Rule-based responses to system events and data changes
- **Multi-Department Organizations**: Isolated rule management with granular permissions
- **Fraud Analytics**: Comprehensive transaction labeling for performance analysis and model improvement

## 📖 Documentation

### Building Documentation

The project uses Sphinx for documentation generation:

```bash
# Build HTML documentation
uv run make html

# View all available documentation formats
uv run make help

# Build other formats
uv run make singlehtml    # Single HTML page
uv run make pdf           # PDF (requires LaTeX)
uv run make epub          # eBook format

# Clean build directory
uv run make clean
```

### Previewing Documentation

After building, preview the documentation locally:

```bash
# Method 1: Using Python's built-in server
cd _build/html
python3 -m http.server 8080
# Then open http://localhost:8080/ in your browser

# Method 2: Direct file access
open _build/html/index.html    # macOS/Linux
# or open _build/html/index.html in your browser

# One-command build and serve
uv run make html && cd _build/html && python3 -m http.server 8080
```

The documentation is also available online at [ReadTheDocs](https://ezrules.readthedocs.io/).

## 🛠️ Development

### Tech Stack

- **Backend**: Python 3.12+, Flask, SQLAlchemy, Celery
- **Frontend**: Next.js, React
- **Database**: PostgreSQL
- **Task Queue**: Celery with Redis/PostgreSQL backend

### Code Quality

```bash
# Run linting and type checking
uv run poe check

# Run tests
uv run pytest
```

### Testing

```bash
# Run tests with coverage
uv run pytest --cov=ezrules

# Generate test data
uv run ezrules generate-random-data

# Clean up test data
uv run ezrules delete-test-data
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.