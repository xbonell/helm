# Day-ahead weather + shared narrative (design)

**Date:** 2026-09-27  
**Status:** approved in chat; awaiting spec file review before implementation

## Goal

Enrich the daily brief weather section with **rest-of-today** and **tomorrow** forecasts per city, and replace per-city LLM narratives with **one shared narrative** covering Barcelona and Sant Cugat.

## Context

- Today each location has `data` (Open-Meteo **current** only), `emoji`, and its own `narrative`.
- Telegram / Hermes summarize per-location lines from that shape.
- Open-Meteo `/v1/forecast` supports `current`, `hourly`, and `daily` in one request.

## Decisions

| Topic | Choice |
|--------|--------|
| Horizon | Current **now** + **rest of today** + **tomorrow** |
| Report shape | Structured fact lines per city, then **one** shared narrative |
| Narrative | Single model-router call; no per-location `narrative` field |
| Timezone | `Europe/Madrid` for today/tomorrow day boundaries |

## Response shape

```json
"sections": {
  "weather": {
    "locations": [
      {
        "name": "Barcelona",
        "emoji": "☁️",
        "now": { "temperature_c": ..., "condition": "...", "wind_speed_kmh": ..., "weather_code": ..., "source": "open-meteo" },
        "today": {
          "date": "YYYY-MM-DD",
          "high_c": ...,
          "low_c": ...,
          "condition": "...",
          "emoji": "...",
          "precip_probability_max": ...,
          "source": "open-meteo"
        },
        "tomorrow": {
          "date": "YYYY-MM-DD",
          "high_c": ...,
          "low_c": ...,
          "condition": "...",
          "emoji": "...",
          "precip_probability_max": ...,
          "source": "open-meteo"
        }
      }
    ],
    "narrative": "One short paragraph covering both cities across now / today / tomorrow.",
    "model": { "provider": "...", "model": "...", "usage": {} }
  }
}
```

Breaking change vs current: drop top-level `data` and per-location `narrative` (callers: smoke script, Hermes routine DESCRIPTION, Telegram formatters).

## Open-Meteo

Per location, one GET with roughly:
- `current=temperature_2m,weather_code,wind_speed_10m`
- `hourly=temperature_2m,weather_code,precipitation_probability` (used to summarize **remaining hours of local today**)
- `daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max` (index 0 = today, 1 = tomorrow in API local timezone — prefer `timezone=Europe/Madrid` for consistency)
- `wind_speed_unit=kmh`

**today** summary: from hourly points with local date = today and time ≥ now (or daily[0] if hourly empty).  
**tomorrow** summary: from `daily` row for tomorrow’s date.

Reuse existing `emoji_for_condition` / WMO map.

## Narrative

One `/v1/generate` call. Prompt includes structured `now` / `today` / `tomorrow` for all locations; ask for **one short paragraph** (no labeled lines). Fallback template if model fails: concatenate deterministic one-liners per city.

## Consumers

- `scripts/generate-daily-brief.sh` — assert `now`/`today`/`tomorrow` + shared `narrative`
- Hermes Daily brief DESCRIPTION — fact lines + Narrative section; Telegram text same shape
- Unit tests for forecast parsing and narrative attachment

## Out of scope

- Multi-day beyond tomorrow
- Hourly charts / graphics
- Per-city narratives
- Changing Decider / non-weather sections

## Acceptance

- Live brief returns both cities with `now`, `today`, `tomorrow`, and a single `narrative`.
- Telegram/Paperclip summary includes structured lines + one narrative block.
- Host smoke passes; unit tests cover parser + emoji on forecast conditions.
