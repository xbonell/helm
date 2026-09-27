#!/usr/bin/env bash
# Milestone 5/6: DecisionEngine via decision-gateway → Decider.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${DECISION_GATEWAY_PORT:-8081}"

echo "POST decision-gateway /v1/decide"
curl -fsS "http://127.0.0.1:${PORT}/v1/decide" \
  -H 'content-type: application/json' \
  -d '{
    "context": "Prepare today'\''s weather report.",
    "candidates": ["personal", "finance", "development", "legal"],
    "criteria": {
      "personal": "Personal assistant, daily brief, weather, calendar, lifestyle",
      "finance": "Money, budgets, invoices, investments",
      "development": "Software, code, repositories, engineering",
      "legal": "Contracts, compliance, legal advice"
    }
  }' | tee /tmp/helm-decide.json

python3 - <<'PY'
import json
body = json.load(open("/tmp/helm-decide.json"))
assert "choice" in body and "confidence" in body and "probabilities" in body
assert body["engine"] == "decider"
assert body["choice"] in {"personal", "finance", "development", "legal"}
print(f"OK typed decision: choice={body['choice']} confidence={body['confidence']}")
# Do not hard-code the expected answer.
PY
