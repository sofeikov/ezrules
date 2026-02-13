# Installation

This page has one recommended path first.
Alternative/manual setup options are in appendices at the end.

## Recommended Path (Most Users)

### Prerequisites

- Python 3.12+
- Docker + Docker Compose
- `uv`
- Git

### 1) Clone and install dependencies

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
uv sync
```

### 2) Start infrastructure

```bash
docker compose up -d
```

Expected:

- PostgreSQL, Redis, and worker containers are up

### 3) Configure `settings.env`

```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules
EZRULES_APP_SECRET=put_your_own_secret_here
EZRULES_ORG_ID=1
```

### 4) Initialize database and permissions

```bash
uv run ezrules init-db
uv run ezrules init-permissions
```

### 5) Create first user

```bash
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

### 6) Verify backend and frontend

Start backend:

--8<-- "snippets/start-api.md"

API docs:

--8<-- "snippets/openapi-links.md"

Start frontend:

```bash
cd ezrules/frontend
npm install
npm start
```

Open [http://localhost:4200](http://localhost:4200).

---

## Next Steps

- UI-first setup validation: [Quick Start](quickstart.md)
- Service/integration validation: [Integration Quickstart](integration-quickstart.md)
- Runtime tuning: [Configuration](configuration.md)

---

## Troubleshooting

Start with [Troubleshooting](../troubleshooting.md).

---

## Appendix A: Install uv

If `uv` is missing:

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

---

## Appendix B: Manual PostgreSQL Setup (Without Docker)

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

=== "Docker single container"

    ```bash
    docker run -d \
      --name ezrules-postgres \
      -e POSTGRES_PASSWORD=yourpassword \
      -e POSTGRES_USER=postgres \
      -p 5432:5432 \
      postgres:16
    ```

If you run manual PostgreSQL, also ensure Redis and worker processes are available if backtesting is required.

---

## Appendix C: Optional Worker Setup

If you do not use Docker Compose for worker management:

```bash
uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
```
