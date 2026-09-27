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
locs = weather["locations"]
assert len(locs) == 2
names = {loc["name"] for loc in locs}
assert names == {"Barcelona", "Sant Cugat del Vallès"}
for loc in locs:
    assert loc["data"]["source"] == "open-meteo"
    assert "temperature_c" in loc["data"]
    assert loc.get("narrative")
assert body["sections"]["agenda"]
assert body["sections"]["priorities"]
assert body["sections"]["fitness"]
print(
    f"OK daily-brief date={body['date']} route={body['routing']['choice']}"
)
for loc in locs:
    print(f"- {loc['name']}: {loc['data']['condition']} {loc['data']['temperature_c']}C")
    print(f"  {loc['narrative']}")
PY
