# Installation

Choose the path that fits your goal.

---

## Path 1 — Demo (exploring the product)

**Prerequisites:** Docker + Docker Compose, Git.

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
docker compose -f docker-compose.demo.yml up --build
```

All services start automatically (PostgreSQL, Redis, Celery worker, API, frontend). The database is seeded with 10 sample rules and 100 events.

| Service | URL |
|---|---|
| Web UI | http://localhost:4200 |
| API | http://localhost:8888 |

Login: `admin@example.com` / `admin`

To reset and re-seed from scratch:

```bash
docker compose -f docker-compose.demo.yml down -v
docker compose -f docker-compose.demo.yml up --build
```

---

## Path 2 — Production (real data)

**Prerequisites:** Docker + Docker Compose, Git.

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
cp .env.example .env
```

Edit `.env` with your own values:

```bash
EZRULES_APP_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
EZRULES_ADMIN_EMAIL=admin@yourorg.com
EZRULES_ADMIN_PASSWORD=<strong password>
```

Then start:

```bash
docker compose -f docker-compose.prod.yml up --build
```

The database is initialised empty. Login with the credentials you set in `.env`.

Data persists in a Docker volume between restarts. To stop without losing data:

```bash
docker compose -f docker-compose.prod.yml down
```

---

## Path 3 — Development (contributing to the project)

**Prerequisites:** Python 3.12+, `uv`, Docker + Docker Compose, Git, Node 20+ (for frontend work).

### 1) Clone and install

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
uv sync
```

### 2) Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL, Redis, and the Celery worker. The API and frontend run as local processes.

### 3) Configure `settings.env`

```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules
EZRULES_APP_SECRET=dev_secret
EZRULES_ORG_ID=1
```

### 4) Initialize database and create first user

```bash
uv run ezrules init-db
uv run ezrules add-user --user-email admin@example.com --password admin --admin
```

### 5) Start API and frontend

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
