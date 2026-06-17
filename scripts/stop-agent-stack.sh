#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=agent-stack-lib.sh
source "${SCRIPT_DIR}/agent-stack-lib.sh"

usage() {
  cat <<'EOF'
Stop API and frontend processes started by ./scripts/start-agent-stack.sh.

Uses recorded PIDs when available, then stops any listeners on the stack ports.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -f "${AGENT_STACK_ENV_FILE}" ]]; then
  load_agent_stack_env
fi

stop_pid() {
  local label="$1"
  local pid="$2"

  if [[ -z "${pid}" ]]; then
    return 0
  fi

  if kill -0 "${pid}" >/dev/null 2>&1; then
    echo "Stopping ${label} (pid ${pid})..."
    kill "${pid}" >/dev/null 2>&1 || true
  fi
}

stop_pid "API" "${API_PID:-}"
stop_pid "frontend shell" "${FRONTEND_PID:-}"

if [[ -n "${API_PORT:-}" ]]; then
  stop_port_listeners "API" "${API_PORT}"
fi

if [[ -n "${FRONTEND_PORT:-}" ]]; then
  stop_port_listeners "frontend" "${FRONTEND_PORT}"
fi

echo "Stopped agent stack processes."
