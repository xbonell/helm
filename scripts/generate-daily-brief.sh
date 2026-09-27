#!/usr/bin/env bash
# Generate the personal-assistant daily brief (Milestones 8–10).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PERSONAL_ASSISTANT_PORT:-8083}"

echo "POST personal-assistant /v1/generate-daily-brief"
curl -fsS "http://127.0.0.1:${PORT}/v1/generate-daily-brief" \
  -H 'content-type: application/json' \
  -d '{}' | tee /tmp/helm-daily-brief.json

python3 - <<'PY'
import json
body = json.load(open("/tmp/helm-daily-brief.json"))
assert body.get("command") == "generate-daily-brief"
assert body.get("date")
assert body["routing"]["choice"] in {"personal", "finance", "development", "legal"}
weather = body["sections"]["weather"]
assert "temperature_c" in weather["data"]
assert weather["data"]["source"] == "open-meteo"
assert weather.get("narrative")
assert body["sections"]["agenda"]
assert body["sections"]["priorities"]
assert body["sections"]["fitness"]
print(
    f"OK daily-brief date={body['date']} route={body['routing']['choice']} "
    f"weather={weather['data']['condition']} {weather['data']['temperature_c']}C"
)
print("--- narrative ---")
print(weather["narrative"])
PY
