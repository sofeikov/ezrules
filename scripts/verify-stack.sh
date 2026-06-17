#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=agent-stack-lib.sh
source "${SCRIPT_DIR}/agent-stack-lib.sh"

TOPOLOGY_ONLY=0

usage() {
  cat <<'EOF'
Verify that a local agent stack is wired correctly for browser login.

Reads .env.agent-stack when present, or uses API_URL / FRONTEND_URL from the
environment. By default also runs a login smoke test (form-encoded OAuth2 fields).

Usage:
  ./scripts/verify-stack.sh [--topology-only]

Options:
  --topology-only  Skip login smoke test (ping, runtime config, CORS only)
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --topology-only)
      TOPOLOGY_ONLY=1
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

if [[ -f "${AGENT_STACK_ENV_FILE}" ]]; then
  load_agent_stack_env
fi

API_URL="${API_URL:-http://127.0.0.1:${API_PORT:-8888}}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:${FRONTEND_PORT:-4200}}"

echo "Verifying stack topology..."
echo "  API:      ${API_URL}"
echo "  Frontend: ${FRONTEND_URL}"

echo "-> API /ping"
curl -fsS "${API_URL}/ping" >/dev/null

echo "-> Frontend runtime-config.js apiUrl"
if [[ ! -f "${RUNTIME_CONFIG_FILE}" ]]; then
  echo "Missing ${RUNTIME_CONFIG_FILE}. Start the frontend with EZRULES_FRONTEND_API_URL set." >&2
  exit 1
fi

if ! grep -Fq "${API_URL}" "${RUNTIME_CONFIG_FILE}"; then
  echo "runtime-config.js does not reference ${API_URL}:" >&2
  cat "${RUNTIME_CONFIG_FILE}" >&2
  exit 1
fi

echo "-> CORS preflight for browser login"
cors_headers="$(
  curl -fsS -X OPTIONS "${API_URL}/api/v2/auth/login" \
    -H "Origin: ${FRONTEND_URL}" \
    -H "Access-Control-Request-Method: POST" \
    -D - -o /dev/null
)"
if ! grep -qi "access-control-allow-origin: ${FRONTEND_URL}" <<<"${cors_headers}"; then
  echo "CORS preflight did not allow origin ${FRONTEND_URL}." >&2
  echo "${cors_headers}" >&2
  exit 1
fi

if [[ "${TOPOLOGY_ONLY}" -eq 0 ]]; then
  echo "-> Login smoke test (username/password form fields)"
  verify_stack_login "${API_URL}"
fi

echo "Stack verification passed."
