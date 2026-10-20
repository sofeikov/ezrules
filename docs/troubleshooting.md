# Troubleshooting

Use this page as the default entry point when local setup, rule testing, or analytics behavior looks wrong.

## API service does not start

**Likely causes**

- `EZRULES_DB_ENDPOINT` is missing or invalid
- PostgreSQL is not running or credentials are wrong
- Port `8888` is already in use

**Diagnose**

```bash
docker compose ps
uv run ezrules api --port 8888
lsof -i :8888          # macOS
ss -ltnp | grep 8888   # Linux
```

**Fix**

1. Start infrastructure: `docker compose up -d`
2. Confirm connection settings in `settings.env`
3. Stop the conflicting process or run API on another port

**Verify**

- `http://localhost:8888/ping` returns a success response
- `http://localhost:8888/docs` opens

## `docker compose` is an unknown command (Linux)

**Likely causes**

- Docker was installed from Ubuntu's `docker.io` package, which does not include the Compose plugin

**Diagnose**

```bash
docker compose version
```

`docker: 'compose' is not a docker command` or `unknown command` means the plugin is missing.

**Fix**

```bash
# Ubuntu's own packages (docker.io)
sudo apt install docker-compose-v2

# Docker's apt repository (docker-ce)
sudo apt install docker-compose-plugin
```

Optionally install `docker-buildx` (or `docker-buildx-plugin` from Docker's repository) to remove the `Docker Compose is configured to build using Bake, but buildx isn't installed` warning on every build.
See [Installation: Linux prerequisites](getting-started/installation.md#linux-prerequisites) for the `docker` group, rootless Docker, and `loginctl enable-linger`.

**Verify**

- `docker compose version` prints a version

## Port `5432` or `6379` is already in use

**Likely causes**

- A PostgreSQL server installed with apt or Homebrew is listening on `5432`
- A Redis server (for example apt's `redis-server`) is listening on `6379`
- A PostgreSQL or Redis container from another project is still running

**Diagnose**

```bash
ss -ltnp | grep -E ':(5432|6379)\b'   # Linux
lsof -i :5432 -i :6379                # macOS
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

`ss` shows the owning process only for your own processes; prefix it with `sudo` to see system services such as `postgres` or `redis-server`.

**Fix**

1. Stop the system services if you want to use the compose containers:

   ```bash
   sudo systemctl disable --now postgresql redis-server   # Ubuntu/Debian
   brew services stop postgresql@16                       # macOS
   ```

2. Or keep the system services and do not start the compose `postgres`/`redis` containers. Make `EZRULES_DB_ENDPOINT` match the system server's credentials (see [Installation: Appendix B](getting-started/installation.md#appendix-b-manual-postgresql-setup-without-docker))
3. Stop containers from other projects that publish the same ports

**Verify**

- `docker compose up -d postgres redis mailpit` starts without a `port is already allocated` or `address already in use` error

## Celery worker or beat exits with `database "ezrules" does not exist`

**Likely causes**

- `docker compose up -d` was run before `uv run ezrules init-db` created the database. The `worker` and `beat` containers have no restart policy, so they stay stopped

**Diagnose**

```bash
docker compose ps -a
docker compose logs worker beat
```

**Fix**

1. Create the database: `uv run ezrules init-db`
2. Start the containers again: `docker compose up -d worker beat`

**Verify**

- `docker compose ps` shows `worker` and `beat` as running

## Angular dev server fails with `ENOSPC` (Linux)

**Likely causes**

- The Angular dev server watches many files and exceeds the inotify limit `fs.inotify.max_user_watches`

**Diagnose**

```bash
cat /proc/sys/fs/inotify/max_user_watches
```

The error reads `ENOSPC: System limit for number of file watchers reached`.

**Fix**

```bash
echo fs.inotify.max_user_watches=524288 | sudo tee /etc/sysctl.d/60-inotify-watches.conf
sudo sysctl --system
```

Then restart `npm start`.

**Verify**

- `npm start` serves the app without the `ENOSPC` error

## Cannot log in to the frontend

**Likely causes**

- No user exists yet
- Wrong password
- API is down, so auth endpoints are unavailable
- Frontend is calling the wrong API port (`runtime-config.js` still points at `http://localhost:8888`)
- CORS blocks the browser login request when frontend and API run on different origins/ports

**Diagnose**

```bash
source .env.agent-stack 2>/dev/null || true
./scripts/verify-stack.sh
curl -fsS "${API_URL:-http://localhost:8888}/ping"
grep apiUrl ezrules/frontend/public/runtime-config.js
curl -fsS -X OPTIONS "${API_URL:-http://localhost:8888}/api/v2/auth/login" \
  -H "Origin: ${FRONTEND_URL:-http://localhost:4200}" \
  -H "Access-Control-Request-Method: POST" -D - -o /dev/null
```

**Fix**

1. Prefer the correlated stack helper:

   ```bash
   docker compose up -d postgres redis mailpit
   ./scripts/start-agent-stack.sh
   ```

2. Create an admin user if needed:

   ```bash
   uv run ezrules bootstrap-org --name your-org --admin-email admin@example.com --admin-password admin
   ```

   Or, if the organisation already exists:

   ```bash
   uv run ezrules add-user --org-name your-org --user-email admin@example.com --password admin --admin
   ```

3. If starting services manually on custom ports, set **all** of these together:
   - API `--port`
   - frontend `npm start -- --port`
   - `EZRULES_FRONTEND_API_URL=http://localhost:<api-port>`
   - `EZRULES_CORS_ALLOWED_ORIGINS=http://localhost:<frontend-port>`
4. Retry login on the frontend URL you actually started (for example `http://localhost:44200/login`)

## Login works via curl but not in the browser

**Likely causes**

- `EZRULES_FRONTEND_API_URL` was not set when starting the Angular dev server
- `EZRULES_CORS_ALLOWED_ORIGINS` does not include the frontend origin
- A stale API process is still listening on `8888` while the frontend targets another port

**Fix**

1. Restart the frontend with `EZRULES_FRONTEND_API_URL` set to the live API URL
2. Restart the API with `EZRULES_CORS_ALLOWED_ORIGINS` set to the frontend origin
3. Run `./scripts/verify-stack.sh` (includes login smoke test by default)
4. Confirm in DevTools → Network that `/api/v2/auth/login` is not blocked by CORS

Login curl (form-encoded OAuth2 fields, not JSON):

```bash
source .env.agent-stack
curl -fsS -X POST "${API_URL}/api/v2/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=${AGENT_STACK_ADMIN_EMAIL}" \
  --data-urlencode "password=${AGENT_STACK_ADMIN_PASSWORD}"
```

**Verify**

- `./scripts/verify-stack.sh` passes
- Browser login reaches the intended API port and returns `200` or `401` (not a CORS error)

## API returns `401` Unauthorized

**Likely causes**

- Missing `Authorization: Bearer <access_token>` header
- Expired access token
- Invalid credentials used during login

**Diagnose**

1. Re-run login and confirm token is returned
2. Confirm header format includes `Bearer` prefix
3. Check whether token refresh/login flow is still valid

**Fix**

1. Obtain a fresh access token from `/api/v2/auth/login`
2. Retry request with updated bearer token
3. If login itself fails, verify email/password and user active status

## API returns `403` Forbidden

**Likely causes**

- User is authenticated but lacks required permission
- Role does not include action needed by endpoint

**Diagnose**

1. Confirm endpoint being called (for example users, roles, audit)
2. Verify user role assignment in **Security** / **Settings**
3. Check role permissions for the relevant resource

**Fix**

1. Assign role with required permission
2. Or update role permissions for the target action
3. Retry with user account that has expected privileges

## Login request returns `422`

**Likely causes**

- Login payload sent as JSON instead of OAuth2 form fields

**Fix**

Use form-encoded payload:

```bash
curl -X POST http://localhost:8888/api/v2/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin"
```

## Rule does not fire

**Likely causes**

- Rule condition does not match payload fields
- Returned outcome is not in allowed outcomes
- Rule was not saved or tested against realistic payload

**Diagnose**

1. Open **Rules**, then open the rule detail page
2. Use **Test Rule** with the exact payload used in your API call
3. Inspect `rule_results`, `outcome_counters`, and `outcome_set` in `/api/v2/evaluate` response

**Fix**

1. Add missing outcome in **Outcomes** first
2. Validate payload field names (`$amount`, `$user_id`, etc.)
3. Save and retest with realistic values

## Analytics charts are empty

**Likely causes**

- No evaluated events in the selected time range
- Rules return no outcomes
- Events are not labeled yet (for label analytics)
- Invalid `aggregation` query value

**Diagnose**

```bash
curl "http://localhost:8888/api/v2/analytics/transaction-volume?aggregation=30d"
curl "http://localhost:8888/api/v2/analytics/outcomes-distribution?aggregation=30d"
curl "http://localhost:8888/api/v2/analytics/labels-summary"
```

**Fix**

1. Submit fresh evaluation events
2. Confirm outcomes exist and rules return those outcomes
3. Label events through `POST /api/v2/labels/mark-event`
4. Use supported aggregation values: `1h`, `6h`, `12h`, `24h`, `30d`

## Backtests stay in `PENDING`

**Likely causes**

- Celery worker is not running
- Redis broker is unavailable

**Diagnose**

```bash
docker compose ps -a
docker compose logs worker
```

**Fix**

1. Start infrastructure with `docker compose up -d`. If the worker exited with `database "ezrules" does not exist`, see [Celery worker or beat exits](#celery-worker-or-beat-exits-with-database-ezrules-does-not-exist)
2. If running manually, start worker:

   ```bash
   uv run celery -A ezrules.backend.tasks worker -l INFO --pool=solo
   ```

## Backend tests fail during DB setup

**Likely causes**

- Another PostgreSQL container is already bound to `localhost:5432`
- Credentials in `EZRULES_DB_ENDPOINT` do not match the running DB
- Test DB name differs from the private database you intended to use (`tests_e2e_<suffix>`)

**Diagnose**

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
echo "$EZRULES_DB_ENDPOINT"
```

**Fix**

1. Use project defaults from `docker-compose.yml` (`postgres:root@localhost:5432`) or update endpoint to match your container credentials
2. Run tests with explicit env vars:

   ```bash
   EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests_e2e_local \
   EZRULES_TESTING=true \
   EZRULES_APP_SECRET=test-secret \
   EZRULES_ORG_ID=1 \
   uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
   ```

## Need deeper setup guidance?

- [Installation](getting-started/installation.md)
- [Configuration](getting-started/configuration.md)
- [Quick Start](getting-started/quickstart.md)
- [Deployment Guide](architecture/deployment.md)
