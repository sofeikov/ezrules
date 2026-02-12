# Installation

This guide will walk you through installing ezrules and its dependencies.

## Prerequisites

Before installing ezrules, ensure you have the following:

- **Python 3.12 or higher**
- **PostgreSQL**
- **Redis** (required for backtesting worker)
- **uv** (Python package manager) - [Installation guide](https://github.com/astral-sh/uv)
- **Git** (for cloning the repository)
- **Docker & Docker Compose** (recommended for local infrastructure)

### Installing uv

If you don't have uv installed:

=== "macOS/Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows"

    ```powershell
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "With pip"

    ```bash
    pip install uv
    ```

### Infrastructure Setup (Recommended: Docker Compose)

From the repository root:

```bash
docker compose up -d
```

This starts PostgreSQL, Redis, and a Celery worker.

### PostgreSQL Setup (Manual)

ezrules requires a PostgreSQL database. You can install PostgreSQL using:

=== "macOS"

    ```bash
    brew install postgresql@16
    brew services start postgresql@16
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt update
    sudo apt install postgresql postgresql-contrib
    sudo systemctl start postgresql
    ```

=== "Docker"

    ```bash
    docker run -d \
      --name ezrules-postgres \
      -e POSTGRES_PASSWORD=yourpassword \
      -e POSTGRES_USER=postgres \
      -p 5432:5432 \
      postgres:16
    ```

---

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
```

### 2. Install Dependencies

ezrules uses `uv` for dependency management:

```bash
uv sync
```

This command will:

- Create a virtual environment
- Install all Python dependencies
- Set up the development environment

### 3. Configure Environment Variables

ezrules reads configuration from `settings.env` by default.

Edit `settings.env` in the project root:

```bash
EZRULES_DB_ENDPOINT="postgresql://postgres:root@localhost:5432/ezrules"
EZRULES_APP_SECRET="put_your_own_secret_here"
EZRULES_ORG_ID=1
```

Or export variables in your shell:

=== "Bash/Zsh"

    ```bash
    export EZRULES_DB_ENDPOINT="postgresql://postgres:yourpassword@localhost:5432/ezrules"
    export EZRULES_APP_SECRET="put_your_own_secret_here"
    export EZRULES_ORG_ID=1
    ```

=== "settings.env"

    Update `settings.env` in the project root:

    ```bash
    EZRULES_DB_ENDPOINT=postgresql://postgres:yourpassword@localhost:5432/ezrules
    EZRULES_APP_SECRET=put_your_own_secret_here
    EZRULES_ORG_ID=1
    ```

!!! tip "Configuration"
    For more configuration options, see the [Configuration Guide](configuration.md).

### 4. Initialize the Database

```bash
# Initialize database (interactive mode)
uv run ezrules init-db

# Or skip prompts with auto-delete
uv run ezrules init-db --auto-delete
```

The `init-db` command will:

- Create the database if it doesn't exist
- Set up all required tables
- Seed default organization, outcomes, and user lists

### 5. Set Up Permissions

Initialize the role-based access control system:

```bash
uv run ezrules init-permissions
```

This creates the default roles:

- **Admin** - Full system access
- **Rule Editor** - Can create/modify rules
- **Read-only** - View-only access

### 6. Create Your First User

```bash
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

!!! warning "Security"
    Change the default password immediately in production environments!

---

## Verify Installation

Start the API service:

--8<-- "snippets/start-api.md"

API documentation links:

--8<-- "snippets/openapi-links.md"

To run the frontend in development:

```bash
cd ezrules/frontend
npm install
npm start
```

Then open [http://localhost:4200](http://localhost:4200).

---

## Optional Components

### Celery Workers (for Background Tasks)

If you need background task processing for rule backtesting:

```bash
# Install Redis (for Celery broker)
brew install redis  # macOS
sudo apt install redis-server  # Ubuntu

# Start Celery workers
uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
```

If you used `docker compose up -d`, the worker is already running.

---

## Next Steps

Now that you have ezrules installed, proceed to the [Quick Start Guide](quickstart.md) to learn how to create your first rule and evaluate events.

---

## Troubleshooting

Start with the [Troubleshooting Guide](../troubleshooting.md).
If the issue is not covered, check [GitHub Issues](https://github.com/sofeikov/ezrules/issues) or file a new one.
