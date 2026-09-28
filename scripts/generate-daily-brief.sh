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
    assert "data" not in loc
    assert "narrative" not in loc
    now = loc["now"]
    assert now["source"] == "open-meteo"
    assert "temperature_c" in now
    assert "condition" in now
    today = loc["today"]
    assert today["source"] == "open-meteo"
    assert "high_c" in today and "low_c" in today
    assert "condition" in today
    assert "precipitation_probability" in today
    tomorrow = loc["tomorrow"]
    assert tomorrow["source"] == "open-meteo"
    assert "date" in tomorrow
    assert "high_c" in tomorrow and "low_c" in tomorrow
    assert "condition" in tomorrow
    assert "precipitation_probability" in tomorrow
assert weather.get("narrative")
assert isinstance(weather["narrative"], str)
assert body["sections"]["agenda"]
assert body["sections"]["priorities"]
assert body["sections"]["fitness"]
print(
    f"OK daily-brief date={body['date']} route={body['routing']['choice']}"
)
for loc in locs:
    n, t, tm = loc["now"], loc["today"], loc["tomorrow"]
    print(
        f"- {loc['emoji']} {loc['name']}: now {n['condition']} {n['temperature_c']}C | "
        f"today {t.get('emoji', '')} {t['condition']} {t['low_c']}–{t['high_c']}C precip {t['precipitation_probability']}% | "
        f"tomorrow {tm.get('emoji', '')} {tm['condition']} {tm['low_c']}–{tm['high_c']}C precip {tm['precipitation_probability']}%"
    )
print(f"Narrative: {weather['narrative'][:200]}")
PY
