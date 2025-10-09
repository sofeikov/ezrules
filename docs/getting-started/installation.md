# Installation

This guide will walk you through installing ezrules and its dependencies.

## Prerequisites

Before installing ezrules, ensure you have the following:

- **Python 3.12 or higher**
- **PostgreSQL 12 or higher**
- **uv** (Python package manager) - [Installation guide](https://github.com/astral-sh/uv)
- **Git** (for cloning the repository)

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

### PostgreSQL Setup

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

### 3. Configure Database Connection

Set the database connection environment variable:

=== "Bash/Zsh"

    ```bash
    export EZRULES_DB_ENDPOINT="postgresql://postgres:yourpassword@localhost:5432/ezrules"
    ```

=== ".env file"

    Create a `.env` file in the project root:

    ```bash
    EZRULES_DB_ENDPOINT=postgresql://postgres:yourpassword@localhost:5432/ezrules
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
- Initialize the schema

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
uv run ezrules add-user --user-email admin@example.com --password admin
```

!!! warning "Security"
    Change the default password immediately in production environments!

---

## Verify Installation

Start the services to verify everything is working:

```bash
# Start the manager service
uv run ezrules manager --port 8888
```

Open your browser to [http://localhost:8888](http://localhost:8888) and log in with your credentials.

---

## Optional Components

### Celery Workers (for Background Tasks)

If you need background task processing for rule backtesting:

```bash
# Install Redis (for Celery broker)
brew install redis  # macOS
sudo apt install redis-server  # Ubuntu

# Start Celery workers
uv run celery -A ezrules.backend.tasks worker -l INFO
```

---

## Next Steps

Now that you have ezrules installed, proceed to the [Quick Start Guide](quickstart.md) to learn how to create your first rule and evaluate events.

---

## Troubleshooting

### Database Connection Issues

If you can't connect to PostgreSQL:

1. Verify PostgreSQL is running:
   ```bash
   pg_isready
   ```

2. Check your connection string format:
   ```
   postgresql://username:password@host:port/database
   ```

3. Ensure the user has permission to create databases

### uv Command Not Found

If `uv` is not found after installation:

1. Restart your shell or run:
   ```bash
   source ~/.bashrc  # or ~/.zshrc
   ```

2. Verify installation:
   ```bash
   uv --version
   ```

### Import Errors

If you encounter import errors when running commands:

1. Ensure you're in the project directory
2. Run `uv sync` again to refresh dependencies
3. Check that your Python version is 3.12+:
   ```bash
   python --version
   ```

For more issues, check our [GitHub Issues](https://github.com/sofeikov/ezrules/issues) or file a new one.
