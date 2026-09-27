#!/usr/bin/env bash
# Ensure Paperclip "Daily brief" routine (07:00 Europe/Madrid → Hermes Runtime).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PAPERCLIP_COMPANY_ID="${PAPERCLIP_COMPANY_ID:-60274e72-d483-4d17-8490-38465207a68a}"
export PAPERCLIP_HERMES_AGENT_ID="${PAPERCLIP_HERMES_AGENT_ID:-d2b84c64-2be4-441f-a601-6a201466e6c5}"
export PAPERCLIP_BOARD_USER_ID="${PAPERCLIP_BOARD_USER_ID:-guPQF8NkqCq1IJS12DUFrqTb2A4eouGf}"
export PAPERCLIP_API_URL="${PAPERCLIP_API_URL:-http://127.0.0.1:3100}"

docker compose cp scripts/lib/ensure-daily-brief-routine.cjs paperclip:/tmp/ensure-daily-brief-routine.cjs

docker compose exec -T \
  -e PAPERCLIP_COMPANY_ID \
  -e PAPERCLIP_HERMES_AGENT_ID \
  -e PAPERCLIP_BOARD_USER_ID \
  -e PAPERCLIP_API_URL \
  paperclip node /tmp/ensure-daily-brief-routine.cjs
