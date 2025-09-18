# ezrules

Open-source transaction monitoring engine for business rules.

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

## Features

- **Rule Engine**: Flexible Python-based rule execution with custom logic support
- **Web Management Interface**: Flask-based UI for creating and managing rules
- **Scalable Architecture**: Multi-service deployment with dedicated manager and evaluator services
- **Database Integration**: PostgreSQL backend with SQLAlchemy ORM and full audit history
- **Backtesting**: Test rule changes against historical data before deployment
- **CLI Tools**: Command-line interface for database management and data generation
- **Frontend Dashboard**: Next.js-based user interface for rule monitoring and analytics

## Architecture

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

## Quick Start

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

# Add a user
uv run ezrules add-user --user-email admin@example.com --password admin
```

### Start Services

```bash
# Start the manager service (web interface)
uv run ezrules manager --port 8888

# Start the evaluator service (API)
uv run ezrules evaluator --port 9999
```

### Generate Test Data

```bash
# Create sample rules and events for testing
uv run ezrules generate-random-data --n-rules 10 --n-events 100
```

## Use Cases

- **Financial Transaction Monitoring**: Real-time fraud detection and compliance checking
- **Business Rule Automation**: Automated decision making based on configurable business logic
- **Event-Driven Processing**: Rule-based responses to system events and data changes
- **Compliance Management**: Ensure transactions meet regulatory requirements

## Development

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

## License

MIT License - see [LICENSE](LICENSE) file for details.