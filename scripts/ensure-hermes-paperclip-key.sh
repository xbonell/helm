#!/usr/bin/env bash
# Ensure Hermes profile has PAPERCLIP_API_KEY so gateway agents can PATCH issues done.
# Idempotent: skips mint when PAPERCLIP_API_KEY already present in data/hermes/.env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PAPERCLIP_COMPANY_ID="${PAPERCLIP_COMPANY_ID:-60274e72-d483-4d17-8490-38465207a68a}"
export PAPERCLIP_HERMES_AGENT_ID="${PAPERCLIP_HERMES_AGENT_ID:-d2b84c64-2be4-441f-a601-6a201466e6c5}"
export PAPERCLIP_BOARD_USER_ID="${PAPERCLIP_BOARD_USER_ID:-guPQF8NkqCq1IJS12DUFrqTb2A4eouGf}"
export PAPERCLIP_API_URL="${PAPERCLIP_API_URL:-http://127.0.0.1:3100}"

if docker compose exec -T hermes sh -c 'grep -q "^PAPERCLIP_API_KEY=.\+" /opt/data/.env 2>/dev/null'; then
  echo "PAPERCLIP_API_KEY already set in Hermes .env — leaving unchanged."
  exit 0
fi

docker compose cp scripts/lib/mint-hermes-paperclip-key.cjs paperclip:/tmp/mint-hermes-paperclip-key.cjs
OUT="$(
  docker compose exec -T \
    -e PAPERCLIP_HERMES_AGENT_ID \
    -e PAPERCLIP_BOARD_USER_ID \
    -e PAPERCLIP_API_URL \
    paperclip node /tmp/mint-hermes-paperclip-key.cjs
)"
TOKEN="$(printf '%s\n' "$OUT" | sed -n 's/^TOKEN=//p' | head -1)"
if [[ -z "$TOKEN" ]]; then
  echo "Failed to mint agent API key" >&2
  printf '%s\n' "$OUT" >&2
  exit 1
fi

docker compose exec -T -u hermes hermes sh -c "
set -e
ENV=/opt/data/.env
touch \"\$ENV\"
grep -vE '^(PAPERCLIP_API_URL|PAPERCLIP_API_KEY|PAPERCLIP_COMPANY_ID|PAPERCLIP_AGENT_ID)=' \"\$ENV\" > /tmp/hermes.env.new || true
printf '%s\n' \
  'PAPERCLIP_API_URL=http://paperclip:3100' \
  \"PAPERCLIP_API_KEY=${TOKEN}\" \
  'PAPERCLIP_COMPANY_ID=${PAPERCLIP_COMPANY_ID}' \
  'PAPERCLIP_AGENT_ID=${PAPERCLIP_HERMES_AGENT_ID}' \
  >> /tmp/hermes.env.new
mv /tmp/hermes.env.new \"\$ENV\"
chmod 600 \"\$ENV\"
"
echo "Wrote PAPERCLIP_API_KEY into Hermes .env; restarting hermes…"
docker compose restart hermes
echo "ok"
