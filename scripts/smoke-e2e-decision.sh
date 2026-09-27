#!/usr/bin/env bash
# Milestone 6: Hermes → DecisionEngine → Decider end-to-end smoke.
# Runs the decision call from inside the Hermes container over Docker DNS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "E2E from hermes container → http://decision-gateway:8081/v1/decide → decider"
docker compose exec -T hermes python3 - <<'PY'
import json, urllib.request

payload = {
    "context": "Prepare today's weather report.",
    "candidates": ["personal", "finance", "development", "legal"],
    "criteria": {
        "personal": "Personal assistant, daily brief, weather, calendar, lifestyle",
        "finance": "Money, budgets, invoices, investments",
        "development": "Software, code, repositories, engineering",
        "legal": "Contracts, compliance, legal advice",
    },
}
req = urllib.request.Request(
    "http://decision-gateway:8081/v1/decide",
    data=json.dumps(payload).encode(),
    headers={"content-type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
    body = json.loads(resp.read().decode())

assert body.get("engine") == "decider"
assert body.get("choice") in payload["candidates"]
print(json.dumps(body, indent=2))
print(f"E2E OK: hermes→decision-gateway→decider choice={body['choice']}")
PY
