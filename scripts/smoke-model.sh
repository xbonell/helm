#!/usr/bin/env bash
# Prove ModelProvider → generated response + usage counters.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${MODEL_ROUTER_PORT:-8082}"

echo "POST model-router /v1/generate"
curl -fsS "http://127.0.0.1:${PORT}/v1/generate" \
  -H 'content-type: application/json' \
  -d '{
    "system": "You write short briefing sections.",
    "prompt": "Summarize: sunny, 22C, light wind. Keep it to one sentence."
  }' | tee /tmp/helm-generate.json

python3 - <<'PY'
import json
body = json.load(open("/tmp/helm-generate.json"))
assert body.get("text"), "missing text"
assert body.get("provider"), "missing provider"
assert body.get("model"), "missing model"
stats = body.get("stats") or {}
assert stats.get("request_count", 0) >= 1
print(
    f"OK generate provider={body['provider']} model={body['model']} "
    f"requests={stats['request_count']} tokens={stats.get('total_tokens')}"
)
PY
