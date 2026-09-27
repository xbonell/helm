#!/usr/bin/env bash
# Manually fire the Paperclip "Daily brief" routine once (smoke / catch-up).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PAPERCLIP_COMPANY_ID="${PAPERCLIP_COMPANY_ID:-60274e72-d483-4d17-8490-38465207a68a}"
export PAPERCLIP_BOARD_USER_ID="${PAPERCLIP_BOARD_USER_ID:-guPQF8NkqCq1IJS12DUFrqTb2A4eouGf}"
export PAPERCLIP_API_URL="${PAPERCLIP_API_URL:-http://127.0.0.1:3100}"
export PAPERCLIP_ROUTINE_TITLE="${PAPERCLIP_ROUTINE_TITLE:-Daily brief}"
export PAPERCLIP_ROUTINE_ID="${PAPERCLIP_ROUTINE_ID:-}"
export PAPERCLIP_WAIT="${PAPERCLIP_WAIT:-1}"

docker compose cp scripts/lib/run-daily-brief-routine.cjs paperclip:/tmp/run-daily-brief-routine.cjs

docker compose exec -T \
  -e PAPERCLIP_COMPANY_ID \
  -e PAPERCLIP_BOARD_USER_ID \
  -e PAPERCLIP_API_URL \
  -e PAPERCLIP_ROUTINE_TITLE \
  -e PAPERCLIP_ROUTINE_ID \
  -e PAPERCLIP_WAIT \
  paperclip node /tmp/run-daily-brief-routine.cjs
