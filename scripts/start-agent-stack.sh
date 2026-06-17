#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=agent-stack-lib.sh
source "${SCRIPT_DIR}/agent-stack-lib.sh"

RESET_DB=1
START_SERVICES=1
VERIFY=1
SUFFIX=""
API_PORT=""
FRONTEND_PORT=""

usage() {
  cat <<'EOF'
Start a disposable local API + Angular stack with correlated ports and env vars.

Writes .env.agent-stack, optionally resets a private database, starts services
in the background, and runs ./scripts/verify-stack.sh.

Usage:
  ./scripts/start-agent-stack.sh [options]

Options:
  --env-only       Write .env.agent-stack and exit without starting services
  --no-reset       Skip reset-dev for the private database. Only use when
                   reusing the same --suffix whose DB was already reset-dev'd
                   in this worktree. A new suffix always needs a full start.
  --no-start       Write env file and reset DB, but do not start API/frontend
  --no-verify      Skip the post-start topology verification
  --suffix VALUE   Stack suffix for DB name ezrules_e2e_<suffix> (default: time-based)
  --api-port PORT  API port (default: random high port)
  --frontend-port PORT
                   Frontend port (default: random high port)
  -h, --help       Show this help

After startup:
  source .env.agent-stack
  open "${FRONTEND_URL}/login"
  ./scripts/verify-stack.sh
  ./scripts/stop-agent-stack.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-only)
      START_SERVICES=0
      RESET_DB=0
      VERIFY=0
      ;;
    --no-reset)
      RESET_DB=0
      ;;
    --no-start)
      START_SERVICES=0
      ;;
    --no-verify)
      VERIFY=0
      ;;
    --suffix)
      SUFFIX="$2"
      shift
      ;;
    --api-port)
      API_PORT="$2"
      shift
      ;;
    --frontend-port)
      FRONTEND_PORT="$2"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

cd "${REPO_ROOT}"
require_stack_prereqs

if [[ -z "${SUFFIX}" ]]; then
  SUFFIX="$(default_stack_suffix)"
fi

if [[ -z "${API_PORT}" ]]; then
  API_PORT="$(find_high_port)"
fi

if [[ -z "${FRONTEND_PORT}" ]]; then
  FRONTEND_PORT="$(find_high_port)"
  while [[ "${FRONTEND_PORT}" == "${API_PORT}" ]]; do
    FRONTEND_PORT="$(find_high_port)"
  done
fi

write_agent_stack_env "${SUFFIX}" "${API_PORT}" "${FRONTEND_PORT}"
load_agent_stack_env

echo "Wrote ${AGENT_STACK_ENV_FILE}"
echo "  API:      ${API_URL} (port ${API_PORT})"
echo "  Frontend: ${FRONTEND_URL} (port ${FRONTEND_PORT})"
echo "  Database: ${EZRULES_DB_ENDPOINT}"

if [[ "${RESET_DB}" -eq 0 ]]; then
  echo "Note: --no-reset skips reset-dev. Use only when ezrules_e2e_${SUFFIX} is already initialized." >&2
fi

if [[ "${RESET_DB}" -eq 1 ]]; then
  echo "-> Resetting private database..."
  EZRULES_DB_ENDPOINT="${EZRULES_DB_ENDPOINT}" \
    EZRULES_TESTING=true \
    EZRULES_APP_SECRET="${EZRULES_APP_SECRET}" \
    EZRULES_ORG_ID="${EZRULES_ORG_ID}" \
    uv run ezrules reset-dev \
      --org-name "${AGENT_STACK_ORG_NAME}" \
      --user-email "${AGENT_STACK_ADMIN_EMAIL}" \
      --password "${AGENT_STACK_ADMIN_PASSWORD}" \
      --n-rules 10 \
      --n-events 100
fi

if [[ "${START_SERVICES}" -eq 0 ]]; then
  echo "Skipping service startup."
  exit 0
fi

"${SCRIPT_DIR}/stop-agent-stack.sh" >/dev/null 2>&1 || true

API_LOG="/tmp/ezrules-agent-api-${SUFFIX}.log"
FRONTEND_LOG="/tmp/ezrules-agent-frontend-${SUFFIX}.log"

echo "-> Starting API..."
API_PID="$(
  EZRULES_DB_ENDPOINT="${EZRULES_DB_ENDPOINT}" \
  EZRULES_APP_SECRET="${EZRULES_APP_SECRET}" \
  EZRULES_ORG_ID="${EZRULES_ORG_ID}" \
  EZRULES_TESTING="${EZRULES_TESTING}" \
  EZRULES_APP_BASE_URL="${EZRULES_APP_BASE_URL}" \
  EZRULES_CORS_ALLOWED_ORIGINS="${EZRULES_CORS_ALLOWED_ORIGINS}" \
  AGENT_STACK_CWD="${REPO_ROOT}" \
  spawn_detached "${API_LOG}" \
    "${VENV_PYTHON}" -m uvicorn ezrules.backend.api_v2.main:app --host 127.0.0.1 --port "${API_PORT}"
)"

echo "-> Starting frontend..."
FRONTEND_PID="$(
  EZRULES_FRONTEND_API_URL="${EZRULES_FRONTEND_API_URL}" \
  AGENT_STACK_CWD="${FRONTEND_DIR}" \
  spawn_detached "${FRONTEND_LOG}" \
    npm start -- --host 127.0.0.1 --port "${FRONTEND_PORT}"
)"

{
  echo "API_PID=${API_PID}"
  echo "FRONTEND_PID=${FRONTEND_PID}"
  echo "API_LOG=${API_LOG}"
  echo "FRONTEND_LOG=${FRONTEND_LOG}"
} >>"${AGENT_STACK_ENV_FILE}"

echo "Waiting for API..."
wait_for_service "${API_URL}/ping" "API" "${API_PID}" "${API_LOG}" 15

echo "Waiting for frontend..."
wait_for_service "${FRONTEND_URL}" "Frontend" "${FRONTEND_PID}" "${FRONTEND_LOG}" 30

if [[ "${VERIFY}" -eq 1 ]]; then
  "${SCRIPT_DIR}/verify-stack.sh"
fi

cat <<EOF

Agent stack is ready.
  Login:    ${FRONTEND_URL}/login
  Email:    ${AGENT_STACK_ADMIN_EMAIL}
  Password: ${AGENT_STACK_ADMIN_PASSWORD}
  API log:  ${API_LOG}
  UI log:   ${FRONTEND_LOG}

To reuse settings in another shell:
  source .env.agent-stack

To stop:
  ./scripts/stop-agent-stack.sh
EOF
