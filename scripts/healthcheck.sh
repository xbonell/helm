#!/usr/bin/env bash
# Health check for Helm stack services.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0

check() {
  local name="$1"
  local url="$2"
  local extra_curl_args=("${@:3}")
  if curl -fsS --max-time 5 "${extra_curl_args[@]}" "$url" >/dev/null 2>&1; then
    printf "%-16s OK\n" "$name"
  else
    printf "%-16s FAIL\n" "$name"
    fail=1
  fi
}

# Load API key for Hermes if present.
HERMES_API_SERVER_KEY="${HERMES_API_SERVER_KEY:-}"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

PAPERCLIP_PORT="${PAPERCLIP_PORT:-3100}"
HERMES_API_PORT="${HERMES_API_PORT:-8642}"
DECISION_GATEWAY_PORT="${DECISION_GATEWAY_PORT:-8081}"

check "Paperclip" "http://127.0.0.1:${PAPERCLIP_PORT}/"
if [[ -n "${HERMES_API_SERVER_KEY:-}" ]]; then
  check "Hermes" "http://127.0.0.1:${HERMES_API_PORT}/health" \
    -H "Authorization: Bearer ${HERMES_API_SERVER_KEY}"
else
  check "Hermes" "http://127.0.0.1:${HERMES_API_PORT}/health"
fi

# Decider is internal-only; probe via docker exec when the container is up.
if docker compose ps --status running --services 2>/dev/null | grep -qx decider; then
  if docker compose exec -T decider python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" \
    >/dev/null 2>&1; then
    printf "%-16s OK\n" "Decider"
  else
    printf "%-16s FAIL\n" "Decider"
    fail=1
  fi
else
  printf "%-16s FAIL\n" "Decider"
  fail=1
fi

check "Decision API" "http://127.0.0.1:${DECISION_GATEWAY_PORT}/health"

MODEL_ROUTER_PORT="${MODEL_ROUTER_PORT:-8082}"
check "Model API" "http://127.0.0.1:${MODEL_ROUTER_PORT}/health"

PERSONAL_ASSISTANT_PORT="${PERSONAL_ASSISTANT_PORT:-8083}"
check "Personal Asst" "http://127.0.0.1:${PERSONAL_ASSISTANT_PORT}/health"

exit "$fail"
