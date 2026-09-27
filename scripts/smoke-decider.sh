#!/usr/bin/env bash
# Smoke-test Decider typed API (POST /v1/systemone + POST /decide).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Decider health:"
docker compose exec -T decider python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10).read().decode())"

echo
echo "POST /v1/systemone:"
docker compose exec -T decision-gateway python -c '
import json, httpx
payload = {
  "state": {"message": "Prepare todays weather report."},
  "questions": {
    "handler": {
      "type": "choice",
      "instructions": "Which agent handler should process this request?",
      "criteria": {
        "personal": "Personal assistant, daily brief, weather, calendar, lifestyle",
        "finance": "Money, budgets, invoices, investments",
        "development": "Software, code, repositories, engineering",
        "legal": "Contracts, compliance, legal advice"
      }
    }
  }
}
r = httpx.post("http://decider:8000/v1/systemone", json=payload, timeout=300.0)
r.raise_for_status()
body = r.json()
print(json.dumps(body, indent=2)[:2000])
choice = body["answers"]["handler"]["choice"]
print("typed choice:", choice)
'

echo
echo "POST /decide:"
docker compose exec -T decision-gateway python -c '
import json, httpx
payload = {
  "context": "Prepare todays weather report.",
  "schema": {
    "handler": {"type": "choice", "options": ["personal", "finance", "development", "legal"]}
  }
}
r = httpx.post("http://decider:8000/decide", json=payload, timeout=300.0)
r.raise_for_status()
print(json.dumps(r.json(), indent=2)[:2000])
'

echo "Decider smoke OK"
