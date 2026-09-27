# Dual-Location Weather Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily brief weather reports Barcelona and Sant Cugat del Vallès as two equal labeled sections, with one model-router call producing both narrative lines.

**Architecture:** Parse `WEATHER_LOCATIONS` into named lat/lon pairs; fetch Open-Meteo per location; one `/v1/generate` call returns two labeled narratives; expose `sections.weather.locations[]` plus shared `model` metadata. Drop single-point lat/lon env and request body fields.

**Tech Stack:** Python 3 FastAPI (`personal-assistant`), httpx, pytest, Docker Compose, existing `model-router` + Open-Meteo.

**Spec:** `docs/superpowers/specs/2026-09-27-dual-location-weather-design.md`

## Global Constraints

- Default locations string (verbatim): `Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864`
- Response shape: `sections.weather = { locations: [...], model: {...} }` — not a bare weather object
- Exactly one model-router generate call per brief for weather narratives when the model is reachable
- Empty/invalid `WEATHER_LOCATIONS` → fail clearly (no silent single-city fallback)
- No per-request location overrides
- Prefer TDD; only commit when the user explicitly asks (do not auto-commit unless requested)

---

## File map

| File | Responsibility |
|------|----------------|
| `services/personal-assistant/locations.py` | Parse `WEATHER_LOCATIONS` → list of `{name, latitude, longitude}` |
| `services/personal-assistant/test_locations.py` | Parser unit tests |
| `services/personal-assistant/brief.py` | Multi-fetch + single narrative generate + assemble `locations` |
| `services/personal-assistant/test_brief_weather.py` | Narrative split + brief weather shape (mocked httpx) |
| `services/personal-assistant/app.py` | Drop lat/lon from `BriefRequest` |
| `services/personal-assistant/weather.py` | Unchanged fetch helper (still used per location) |
| `compose.yaml` / `.env.example` / `.env` | `WEATHER_LOCATIONS`; remove lat/lon |
| `scripts/generate-daily-brief.sh` | Assert both cities |
| `scripts/lib/ensure-daily-brief-routine.cjs` | Hermes comment both cities |
| `README.md` | Document `WEATHER_LOCATIONS` |

---

### Task 1: Parse `WEATHER_LOCATIONS`

**Files:**
- Create: `services/personal-assistant/locations.py`
- Create: `services/personal-assistant/test_locations.py`

**Interfaces:**
- Produces: `parse_weather_locations(raw: str) -> list[WeatherLocation]` where `WeatherLocation` is a frozen dataclass with `name: str`, `latitude: float`, `longitude: float`
- Produces: `WeatherLocationError(ValueError)` on empty/invalid input

- [ ] **Step 1: Write failing tests**

```python
# services/personal-assistant/test_locations.py
import pytest
from locations import WeatherLocation, WeatherLocationError, parse_weather_locations

DEFAULT = "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864"

def test_parse_default_two_cities():
    locs = parse_weather_locations(DEFAULT)
    assert locs == [
        WeatherLocation(name="Barcelona", latitude=41.3874, longitude=2.1686),
        WeatherLocation(name="Sant Cugat del Vallès", latitude=41.4728, longitude=2.0864),
    ]

def test_parse_rejects_empty():
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("")
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("   ")

def test_parse_rejects_malformed():
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("Barcelona")
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("Barcelona:41.3874")
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd services/personal-assistant && python -m pytest test_locations.py -v
```

Expected: FAIL (module not found / import error)

- [ ] **Step 3: Implement parser**

```python
# services/personal-assistant/locations.py
from __future__ import annotations
from dataclasses import dataclass

class WeatherLocationError(ValueError):
    pass

@dataclass(frozen=True)
class WeatherLocation:
    name: str
    latitude: float
    longitude: float

def parse_weather_locations(raw: str) -> list[WeatherLocation]:
    text = (raw or "").strip()
    if not text:
        raise WeatherLocationError("WEATHER_LOCATIONS is empty")
    out: list[WeatherLocation] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise WeatherLocationError(f"missing ':' in location entry: {part!r}")
        name, coords = part.rsplit(":", 1)
        name = name.strip()
        coords = coords.strip()
        if not name or "," not in coords:
            raise WeatherLocationError(f"invalid location entry: {part!r}")
        lat_s, lon_s = coords.split(",", 1)
        try:
            lat = float(lat_s.strip())
            lon = float(lon_s.strip())
        except ValueError as exc:
            raise WeatherLocationError(f"invalid coordinates in {part!r}") from exc
        out.append(WeatherLocation(name=name, latitude=lat, longitude=lon))
    if not out:
        raise WeatherLocationError("WEATHER_LOCATIONS produced no locations")
    return out
```

Use `rsplit(":", 1)` so names never contain a second colon issue; names with spaces are fine.

- [ ] **Step 4: Run tests — expect pass**

```bash
cd services/personal-assistant && python -m pytest test_locations.py -v
```

Expected: PASS (3 tests)

---

### Task 2: Multi-location brief weather + one narrative call

**Files:**
- Modify: `services/personal-assistant/brief.py`
- Create: `services/personal-assistant/test_brief_weather.py`

**Interfaces:**
- Consumes: `parse_weather_locations`, `fetch_weather`, existing `WeatherSnapshot.as_dict()`
- Produces: `split_location_narratives(text: str, names: list[str]) -> dict[str, str]`
- Produces: `generate_daily_brief(...)` returns `sections.weather.locations` list; removes lat/lon parameters
- Produces: `render_multi_weather_narratives(snapshots: list[tuple[str, WeatherSnapshot]], model_url: str) -> dict`

- [ ] **Step 1: Write failing tests for narrative split + section shape**

```python
# services/personal-assistant/test_brief_weather.py
from brief import split_location_narratives

def test_split_labeled_lines():
    text = (
        "Barcelona: Overcast, 24C with light wind.\n"
        "Sant Cugat del Vallès: Clear, 22C."
    )
    got = split_location_narratives(
        text, ["Barcelona", "Sant Cugat del Vallès"]
    )
    assert "Overcast" in got["Barcelona"]
    assert "Clear" in got["Sant Cugat del Vallès"]

def test_split_fallback_when_unlabeled():
    got = split_location_narratives("just one blob", ["Barcelona", "Sant Cugat del Vallès"])
    assert got["Barcelona"]  # non-empty fallback later filled by caller; here expect empty or blob rules
```

Implement split so that:
- For each name, find a line starting with `Name:` or `Name -` (case-sensitive match on configured name)
- If a name has no matching line, return `""` for that name (caller applies template fallback)

Adjust the second test to:

```python
def test_split_missing_label_returns_empty():
    got = split_location_narratives("unrelated prose", ["Barcelona", "Sant Cugat del Vallès"])
    assert got["Barcelona"] == ""
    assert got["Sant Cugat del Vallès"] == ""
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd services/personal-assistant && python -m pytest test_brief_weather.py -v
```

Expected: FAIL import / missing function

- [ ] **Step 3: Implement split + rewrite `brief.py` weather path**

Add to `brief.py` (replace single-location weather path):

```python
def split_location_narratives(text: str, names: list[str]) -> dict[str, str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = {name: "" for name in names}
    for name in names:
        for ln in lines:
            for prefix in (f"{name}:", f"{name} -", f"{name} –"):
                if ln.startswith(prefix):
                    out[name] = ln[len(prefix):].strip()
                    break
            if out[name]:
                break
    return out

def _template_narrative(name: str, weather: WeatherSnapshot) -> str:
    return (
        f"{name}: {weather.condition}, {weather.temperature_c}°C, "
        f"wind {weather.wind_speed_kmh} km/h."
    )

def render_multi_weather_narratives(
    named: list[tuple[str, WeatherSnapshot]],
    model_url: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    payload_lines = []
    for name, snap in named:
        payload_lines.append(f"{name}: {snap.as_dict()}")
    names = [n for n, _ in named]
    name_list = ", ".join(names)
    prompt = (
        "Write exactly one short briefing sentence per location from this weather data. "
        f"Output exactly {len(names)} lines, each starting with the location name "
        f"followed by a colon. Location names in order: {name_list}. No preamble.\n"
        + "\n".join(payload_lines)
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{model_url.rstrip('/')}/v1/generate",
            json={
                "system": "You write concise personal daily brief weather lines.",
                "prompt": prompt,
                "max_tokens": 200,
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        return response.json()
```

In `generate_daily_brief`:
- Remove `latitude` / `longitude` parameters
- `raw = os.environ.get("WEATHER_LOCATIONS", "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864")`
- `locations = parse_weather_locations(raw)`
- Fetch each; call `render_multi_weather_narratives` once
- `narratives = split_location_narratives(gen.get("text") or "", [loc.name for loc in locations])`
- For each location, if narrative empty, use `_template_narrative`
- Build:

```python
"weather": {
    "locations": [
        {"name": loc.name, "data": snap.as_dict(), "narrative": narratives[loc.name] or _template_narrative(loc.name, snap)}
        for loc, snap in zip(locations, snapshots)
    ],
    "model": {
        "provider": weather_gen.get("provider"),
        "model": weather_gen.get("model"),
        "usage": weather_gen.get("usage"),
    },
}
```

Remove old `render_weather_section` single-city helper if unused, or keep unused only if tests still import it — delete if unused.

Import `parse_weather_locations` / `WeatherLocationError` from `locations`. Let `WeatherLocationError` propagate to `app.py` as 502 (already wraps Exception).

- [ ] **Step 4: Run unit tests**

```bash
cd services/personal-assistant && python -m pytest test_locations.py test_brief_weather.py test_weather.py -v
```

Expected: PASS

---

### Task 3: API + Compose + env

**Files:**
- Modify: `services/personal-assistant/app.py`
- Modify: `compose.yaml` (personal-assistant `environment`)
- Modify: `.env.example`
- Modify: `.env` (local; do not commit)

**Interfaces:**
- Consumes: `generate_daily_brief()` with no lat/lon
- Produces: `BriefRequest` empty model (or no body fields)

- [ ] **Step 1: Simplify API**

```python
class BriefRequest(BaseModel):
    pass

@app.post("/v1/generate-daily-brief")
def daily_brief(body: BriefRequest | None = None) -> dict[str, Any]:
    try:
        return generate_daily_brief()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

- [ ] **Step 2: Compose / env**

In `compose.yaml` personal-assistant environment, replace lat/lon with:

```yaml
WEATHER_BASE_URL: ${WEATHER_BASE_URL:-https://api.open-meteo.com}
WEATHER_LOCATIONS: ${WEATHER_LOCATIONS:-Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864}
```

In `.env.example`:

```bash
WEATHER_BASE_URL=https://api.open-meteo.com
# name:lat,lon entries separated by ;
WEATHER_LOCATIONS=Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864
```

Remove `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` from `.env.example` and from local `.env`.

- [ ] **Step 3: Rebuild personal-assistant**

```bash
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose up -d --build personal-assistant
EOF
```

Expected: container healthy

---

### Task 4: Smoke script, Hermes routine text, README

**Files:**
- Modify: `scripts/generate-daily-brief.sh`
- Modify: `scripts/lib/ensure-daily-brief-routine.cjs` (`DESCRIPTION`)
- Modify: `README.md` (daily brief / weather note)

- [ ] **Step 1: Update host smoke assertions**

Replace weather asserts with:

```python
weather = body["sections"]["weather"]
locs = weather["locations"]
assert len(locs) == 2
names = {loc["name"] for loc in locs}
assert names == {"Barcelona", "Sant Cugat del Vallès"}
for loc in locs:
    assert loc["data"]["source"] == "open-meteo"
    assert "temperature_c" in loc["data"]
    assert loc.get("narrative")
print("OK daily-brief ...")
for loc in locs:
    print(f"- {loc['name']}: {loc['data']['condition']} {loc['data']['temperature_c']}C")
    print(f"  {loc['narrative']}")
```

- [ ] **Step 2: Update routine DESCRIPTION weather bullet**

In `ensure-daily-brief-routine.cjs`, change step 2 comment instructions to require both cities from `sections.weather.locations` (name, condition/temp, narrative each).

- [ ] **Step 3: Re-ensure routine + host smoke**

```bash
./scripts/ensure-daily-brief-routine.sh
./scripts/generate-daily-brief.sh
```

Expected: OK print with both Barcelona and Sant Cugat lines

- [ ] **Step 4: README**

Document `WEATHER_LOCATIONS` default (Barcelona + Sant Cugat) where daily brief / env is described; remove single lat/lon wording.

---

## Spec coverage check

| Spec requirement | Task |
|------------------|------|
| `WEATHER_LOCATIONS` named list default | 1, 3 |
| Remove single lat/lon | 2, 3 |
| `sections.weather.locations[]` + shared `model` | 2 |
| One model-router call | 2 |
| Narrative parse + template fallback | 2 |
| No request overrides | 3 |
| Invalid list fails | 1, 2 |
| Smoke + Hermes description + README | 4 |

## Placeholder / consistency check

- Parser uses `rsplit(":", 1)` consistently for names with spaces
- Default string identical in compose, `.env.example`, and `generate_daily_brief` fallback
- Smoke expects exactly the two default names
