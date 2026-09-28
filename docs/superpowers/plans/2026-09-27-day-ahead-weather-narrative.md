# Day-Ahead Weather + Shared Narrative Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rest-of-today and tomorrow forecasts per city, and one shared weather narrative covering both locations for the daily brief (Paperclip + Telegram).

**Architecture:** Extend Open-Meteo fetch to `current` + `hourly` + `daily` with `timezone=Europe/Madrid`; reshape each location to `now`/`today`/`tomorrow`; one model-router call for a single `sections.weather.narrative`. Update smoke and Hermes routine text.

**Tech Stack:** Open-Meteo, personal-assistant Python, pytest, existing model-router, Paperclip Routine DESCRIPTION.

**Spec:** `docs/superpowers/specs/2026-09-27-day-ahead-weather-narrative-design.md`

## Global Constraints

- Horizon: **now** + **rest of today** + **tomorrow** (not multi-day beyond that)
- Report: structured fact lines per city, then **one** shared narrative
- Timezone for day boundaries: `Europe/Madrid`
- Breaking: remove per-location `data` and `narrative`; add `now`/`today`/`tomorrow` + top-level `narrative`
- Prefer TDD; commit only when the user asks

---

## File map

| File | Responsibility |
|------|----------------|
| `services/personal-assistant/weather.py` | Fetch + parse Open-Meteo into structured periods |
| `services/personal-assistant/test_weather.py` | Parser tests with fixture JSON |
| `services/personal-assistant/brief.py` | Assemble locations + shared narrative |
| `services/personal-assistant/test_brief_weather.py` | Narrative + shape tests |
| `scripts/generate-daily-brief.sh` | Smoke asserts |
| `scripts/lib/ensure-daily-brief-routine.cjs` | Hermes/Telegram summary format |

---

### Task 1: Open-Meteo fetch + period summaries

**Files:**
- Modify: `services/personal-assistant/weather.py`
- Modify: `services/personal-assistant/test_weather.py`

**Interfaces:**
- Produces: `fetch_weather_bundle(lat, lon, *, base_url, tz="Europe/Madrid") -> WeatherBundle`
- `WeatherBundle` with `.now`, `.today`, `.tomorrow` dicts (or small dataclasses with `.as_dict()`)
- Keep `WeatherSnapshot` for `now` or fold into dicts — prefer dataclasses `WeatherNow`, `WeatherDaySummary`

- [ ] **Step 1: Write failing tests** using a frozen Open-Meteo-like fixture (hourly spanning today, daily[0]/daily[1])

Assert `tomorrow.date`, `tomorrow.high_c` / `low_c`, `today` uses only hours ≥ “now” in fixture, conditions map via existing WMO helpers.

- [ ] **Step 2: Run tests — expect fail**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_weather.py -v
```

- [ ] **Step 3: Implement fetch**

Request params:

```python
{
  "latitude": lat,
  "longitude": lon,
  "current": "temperature_2m,weather_code,wind_speed_10m",
  "hourly": "temperature_2m,weather_code,precipitation_probability",
  "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
  "wind_speed_unit": "kmh",
  "timezone": "Europe/Madrid",
}
```

Parse:
- `now` from `current`
- `today` from hourly where local date == today and datetime ≥ now (max/min temp, mode/majority weather_code, max precip_probability); if no remaining hours, fall back to `daily[0]`
- `tomorrow` from the `daily` row whose `time` == tomorrow’s date

Expose `as_dict()` on each period including `condition` (WMO string) and `source: open-meteo`.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit only if user asks**

---

### Task 2: Brief assembly — shared narrative

**Files:**
- Modify: `services/personal-assistant/brief.py`
- Modify: `services/personal-assistant/test_brief_weather.py`

**Interfaces:**
- Consumes: `fetch_weather_bundle`, `emoji_for_condition`
- Produces: `sections.weather.locations[]` with `name`, `emoji` (from `now.condition`), `now`, `today`, `tomorrow` (each dict includes period emoji optional — set `emoji` on today/tomorrow via condition)
- Produces: `sections.weather.narrative: str` (single)
- Remove: `split_location_narratives` usage for per-city narratives; delete or stop calling `render_multi_weather_narratives` labeled-lines API

- [ ] **Step 1: Failing tests** for shape + that `render_shared_weather_narrative` prompt asks for one paragraph; mock httpx generate

- [ ] **Step 2: Implement**

```python
def render_shared_weather_narrative(locations_payload: list[dict], model_url: str) -> dict:
    prompt = (
        "Write one short paragraph (2–4 sentences) for a morning personal brief. "
        "Cover both locations' current conditions, the rest of today, and tomorrow. "
        "No bullet list, no preamble, no location-labeled lines.\n"
        f"{locations_payload}"
    )
    ...
```

Fallback template if empty text: join short deterministic sentences per city.

Location object:

```python
{
  "name": loc.name,
  "emoji": emoji_for_condition(bundle.now.condition),
  "now": {**bundle.now.as_dict()},
  "today": {**bundle.today.as_dict(), "emoji": emoji_for_condition(bundle.today.condition)},
  "tomorrow": {**bundle.tomorrow.as_dict(), "emoji": emoji_for_condition(bundle.tomorrow.condition)},
}
```

- [ ] **Step 3: Full unit suite green**

```bash
uv run --with pytest --with httpx pytest test_weather.py test_brief_weather.py test_weather_emoji.py test_locations.py -v
```

- [ ] **Step 4: Rebuild PA + curl smoke of JSON keys**

```bash
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose up -d --build personal-assistant
EOF
/usr/bin/curl -fsS http://127.0.0.1:8083/v1/generate-daily-brief -H 'content-type: application/json' -d '{}' \
  | python3 -c "import json,sys; w=json.load(sys.stdin)['sections']['weather']; assert 'narrative' in w; assert 'data' not in w['locations'][0]; assert 'tomorrow' in w['locations'][0]; print(w['narrative'][:200]); print([(l['name'], l['now']['condition'], l['tomorrow'].get('high_c')) for l in w['locations']])"
```

---

### Task 3: Smoke script + Hermes / Telegram copy

**Files:**
- Modify: `scripts/generate-daily-brief.sh`
- Modify: `scripts/lib/ensure-daily-brief-routine.cjs` (`DESCRIPTION` summary steps)
- Modify: `docs/telegram-daily-brief.md` if it shows sample message shape (brief note)

**Summary format for Hermes/Telegram:**

```
Weather
{emoji} {name} — now: {cond}, {temp}°C | today: {emoji} {cond}, {low}–{high}°C, precip {p}% | tomorrow: {emoji} {cond}, {low}–{high}°C, precip {p}%
…
Narrative
{sections.weather.narrative}
```

- [ ] **Step 1: Update smoke asserts** for `now`/`today`/`tomorrow` + `narrative`
- [ ] **Step 2: Update DESCRIPTION** steps 2–4 accordingly; re-ensure + force DB sync
- [ ] **Step 3: `./scripts/generate-daily-brief.sh`** passes
- [ ] **Step 4: Optional `./scripts/run-daily-brief-routine.sh`** — confirm Telegram DM shape (if Hermes up)

---

## Spec coverage

| Spec | Task |
|------|------|
| now + today + tomorrow | 1, 2 |
| Shared narrative | 2 |
| Europe/Madrid | 1 |
| Breaking shape / consumers | 2, 3 |
| Emoji on conditions | 2 |

## Consistency

- Default locations unchanged (`WEATHER_LOCATIONS`)
- One model call for weather narrative
- No secrets in repo
