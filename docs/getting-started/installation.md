# Installation

Choose the path that fits your goal.

All three paths need Docker with the Compose plugin. On Linux, read [Linux prerequisites](#linux-prerequisites) first: most distributions do not install Compose together with Docker.

---

## Linux prerequisites

Docker Desktop (macOS, Windows) already includes Compose and Buildx. On Linux, the Docker engine and its plugins are separate packages.

**Docker Compose plugin.** Ubuntu's `docker.io` package does not include Compose, so `docker compose` fails with `unknown command`. Install the plugin:

```bash
# Ubuntu's own packages (docker.io)
sudo apt install docker-compose-v2

# Docker's apt repository (docker-ce)
sudo apt install docker-compose-plugin
```

Check it with `docker compose version`.

**Buildx (optional).** Without Buildx every build prints `Docker Compose is configured to build using Bake, but buildx isn't installed`. Builds still work. To remove the warning, install `docker-buildx` (Ubuntu packages) or `docker-buildx-plugin` (Docker's apt repository).

**Running Docker without `sudo`.** With the standard (rootful) daemon, add your user to the `docker` group, then log out and back in:

```bash
sudo usermod -aG docker "$USER"
```

Rootless Docker works as-is: the published ports (`4200`, `8888`, `5432`, `6379`, `8025`) are reachable on `localhost`. Rootless containers stop when you log out unless lingering is enabled for your user:

```bash
sudo loginctl enable-linger "$USER"
```

**Ports already in use.** The compose files publish PostgreSQL on `5432` and Redis on `6379`. If PostgreSQL or Redis is already installed from apt and running, the containers cannot start. See [Appendix B](#appendix-b-manual-postgresql-setup-without-docker) and [Troubleshooting](../troubleshooting.md#port-5432-or-6379-is-already-in-use).

---

## Path 1 — Demo (exploring the product)

**Prerequisites:** Docker + Docker Compose, Git. On Linux, see [Linux prerequisites](#linux-prerequisites).

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
docker compose -f docker-compose.demo.yml up --build
```

All services start automatically (PostgreSQL, Redis, Celery worker, Celery beat, API, frontend). The database is seeded with 10 sample rules and 100 events.
If you re-run the same command later, the demo database is recreated from scratch so older persisted schemas do not break the stack.

| Service | URL |
|---|---|
| Web UI | http://localhost:4200 |
| API | http://localhost:8888 |
| Mailpit UI (captured emails) | http://localhost:8025 |

Login: `admin@example.com` / `admin`

To reset and re-seed from scratch:

```bash
docker compose -f docker-compose.demo.yml down -v
docker compose -f docker-compose.demo.yml up --build
```

---

## Path 2 — Single-Host Production Validation

**Prerequisites:** Docker + Docker Compose, Git. On Linux, see [Linux prerequisites](#linux-prerequisites).

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
cp .env.example .env
```

Edit `.env` with your own values:

```bash
EZRULES_APP_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
EZRULES_ORG_NAME=your-org
EZRULES_ADMIN_EMAIL=admin@yourorg.com
EZRULES_ADMIN_PASSWORD=<strong password>
```

Then start:

```bash
docker compose -f docker-compose.prod.yml up --build
```

The database is initialised empty. Login with the credentials you set in `.env`.
By default, SMTP is routed to local Mailpit (`http://localhost:8025`) unless SMTP env vars override it.
Re-running the same command later keeps the existing Docker volume and applies pending migrations before the stack starts.
Keep the same `EZRULES_APP_SECRET` for every upgrade. Stored notification and organisation-specific AI credentials are encrypted with it, and the migration process must receive the real value rather than a generated replacement.

Use this single-host stack to validate the production images locally. If you want an AWS-oriented deployment example, follow [Deployment Guide](../architecture/deployment.md) for the documented ECS/Fargate topology.

Data persists in a Docker volume between restarts. To stop without losing data:

```bash
docker compose -f docker-compose.prod.yml down
```

---

## Path 3 — Development (contributing to the project)

**Prerequisites:** Python 3.12+, `uv`, Docker + Docker Compose, Git, Node 20+ (for frontend work). On Linux, see [Linux prerequisites](#linux-prerequisites).

### 1) Clone and install

```bash
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
uv sync
```

### 2) Start infrastructure

```bash
docker compose up -d postgres redis mailpit
```

This starts PostgreSQL, Redis, and Mailpit (local email capture on `http://localhost:8025`). The API and frontend run as local processes.
The Celery worker and Celery beat are started in step 4, after the database exists.

!!! warning "Do not start the worker and beat yet"
    A bare `docker compose up -d` also starts the `worker` and `beat` containers. They connect to the `ezrules` database, which does not exist until `ezrules init-db` runs, so both exit with `database "ezrules" does not exist`. They have no restart policy and stay down. If this already happened, run `docker compose up -d` again after step 4.

### 3) Configure `settings.env`

```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/ezrules
EZRULES_APP_SECRET=dev_secret
EZRULES_CORS_ALLOWED_ORIGINS=http://localhost:4200
EZRULES_SMTP_HOST=localhost
EZRULES_SMTP_PORT=1025
EZRULES_FROM_EMAIL=no-reply@ezrules.local
EZRULES_APP_BASE_URL=http://localhost:4200
EZRULES_AI_AUTHORING_MODEL=gpt-4.1-mini
EZRULES_AI_AUTHORING_API_KEY=provider-api-key
```

The `worker` and `beat` containers do not read `settings.env`. `docker-compose.yml` sets their environment directly:

- `EZRULES_DB_ENDPOINT=postgresql://postgres:root@postgres:5432/ezrules` (the database name `ezrules` is fixed)
- `EZRULES_APP_SECRET=put_your_own_secret_here`

The `settings.env` in the repository uses `EZRULES_APP_SECRET=dev_secret`, so by default the local API and the Celery containers use different secrets. Stored notification channel settings and organisation-specific AI provider credentials are encrypted with `EZRULES_APP_SECRET`. Values that the API encrypts with one secret cannot be decrypted by worker tasks that use the other (for example, alert notification delivery). If you use those features locally, set the same value in both places, and keep the database name `ezrules` unless you also change `docker-compose.yml`.

### 4) Initialize database and bootstrap the first organisation

```bash
uv run ezrules init-db
uv run ezrules bootstrap-org --name your-org --admin-email admin@example.com --admin-password admin
```

Now that the database exists, start the Celery worker and beat:

```bash
docker compose up -d worker beat
```

Check that they are running with `docker compose ps`. If either shows `Exited`, read its log with `docker compose logs worker`.

`init-db` creates the target database (if missing), applies Alembic migrations, and initializes the global permission action catalogue.
`bootstrap-org` creates the organisation, seeds default roles and user lists, and creates the first admin user.
It does not create any outcomes or labels; add those through the UI or API for each environment.
After pulling future schema changes, export the deployment's stable `EZRULES_APP_SECRET` and run `uv run alembic upgrade head` on existing databases.

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
On Linux, if `npm start` fails with `ENOSPC: System limit for number of file watchers reached`, see [Troubleshooting](../troubleshooting.md#angular-dev-server-fails-with-enospc-linux).
For invitation/password-reset email testing, open [http://localhost:8025](http://localhost:8025).

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

The rest of this guide assumes the endpoint `postgresql://postgres:root@localhost:5432/ezrules`. Either give the `postgres` user the password `root`, as shown below, or change `EZRULES_DB_ENDPOINT` in `settings.env` to match your server.

!!! warning "Do not run both a system PostgreSQL and the compose PostgreSQL"
    A PostgreSQL server installed with Homebrew or apt listens on `5432`, the same port that `docker-compose.yml` publishes. If both are present, `docker compose up` fails with a port conflict, or the API connects to the server you did not mean to use. Use one or the other. The same applies to a Redis server (for example apt's `redis-server`) on `6379`. To switch back to the compose services on Ubuntu/Debian, stop the system services first:

    ```bash
    sudo systemctl disable --now postgresql redis-server
    ```

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
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'root';"
    ```

    For backtesting and other Celery work, also install Redis:

    ```bash
    sudo apt install redis-server
    ```

=== "Docker single container"

    ```bash
    docker run -d \
      --name ezrules-postgres \
      -e POSTGRES_PASSWORD=root \
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
uv run celery -A ezrules.backend.tasks beat -l INFO
```
