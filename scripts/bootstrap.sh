#!/usr/bin/env bash
# Bootstrap local Helm stack: secrets, data dirs, Hermes seed config.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p data/paperclip data/hermes data/decider-hf data/backups

if [[ ! -f .env ]]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
    hermes_key="$(openssl rand -hex 32)"
    # Portable in-place replace without requiring GNU sed.
    tmp="$(mktemp)"
    sed \
      -e "s|^BETTER_AUTH_SECRET=.*|BETTER_AUTH_SECRET=${secret}|" \
      -e "s|^HERMES_API_SERVER_KEY=.*|HERMES_API_SERVER_KEY=${hermes_key}|" \
      .env >"$tmp"
    mv "$tmp" .env
    echo "Generated BETTER_AUTH_SECRET and HERMES_API_SERVER_KEY in .env"
  else
    echo "Created .env from .env.example — set BETTER_AUTH_SECRET and HERMES_API_SERVER_KEY manually."
  fi
else
  echo ".env already exists — leaving it unchanged."
fi

# Seed minimal Hermes config if missing (non-interactive; avoids setup wizard).
if [[ ! -f data/hermes/config.yaml ]]; then
  cat >data/hermes/config.yaml <<'EOF'
# Seeded by scripts/bootstrap.sh — edit as needed.
# Model provider details typically live in data/hermes/.env
# Unattended Paperclip wakes need approvals.mode off (or curl on command_allowlist).
approvals:
  mode: off
EOF
  echo "Seeded data/hermes/config.yaml"
fi

if [[ ! -f data/hermes/.env ]]; then
  # Mirror API server key into Hermes profile env so gateway API auth matches compose.
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
  cat >data/hermes/.env <<EOF
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=${HERMES_API_SERVER_KEY}
EOF
  echo "Seeded data/hermes/.env"
fi

echo "Bootstrap complete. Next: docker compose up -d"
