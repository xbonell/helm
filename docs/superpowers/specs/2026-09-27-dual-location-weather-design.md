# Dual-location weather in daily brief (design)

**Date:** 2026-09-27  
**Status:** approved in chat; awaiting spec file review before implementation plan

## Goal

Daily brief weather reports **Barcelona** and **Sant Cugat del Vallès** as two equal labeled sections, each with structured Open-Meteo data and a short narrative line, using **one** `model-router` call for both narratives.

## Context

- Today `personal-assistant` fetches a single lat/lon from `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` (Barcelona defaults) and builds `sections.weather` as one object (`data` + `narrative` + `model`).
- Open-Meteo remains the weather source; no API key.
- Hermes Routine comments and `scripts/generate-daily-brief.sh` assume a single weather block today.

## Decisions (from brainstorming)

| Topic | Choice |
|--------|--------|
| Presentation | Two equal labeled sections |
| Narratives | One LLM call covering both snapshots; two labeled lines |
| Configuration | Fixed named list in env (`WEATHER_LOCATIONS`); no per-request override |
| Response shape | Wrap: `sections.weather = { locations: [...], model: {...} }` |

## Configuration

Replace single-point env with:

```bash
WEATHER_LOCATIONS=Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864
```

Format: `Name:lat,lon` entries separated by `;`. Names may contain spaces; `:` separates name from coordinates; `,` separates lat and lon.

- Compose passes `WEATHER_LOCATIONS` into `personal-assistant`.
- Remove `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` from compose / `.env.example` (single source of truth).
- Invalid / empty list → fail the brief with a clear 502/detail (do not silently fall back to Barcelona-only).

Sant Cugat coordinates default: **41.4728, 2.0864** (city center approx.).

## API / response shape

`POST /v1/generate-daily-brief` accepts `{}` only. Drop `latitude` / `longitude` from the request body.

```json
"sections": {
  "weather": {
    "locations": [
      {
        "name": "Barcelona",
        "data": { "latitude": ..., "longitude": ..., "temperature_c": ..., "wind_speed_kmh": ..., "condition": "...", "weather_code": ..., "source": "open-meteo" },
        "narrative": "…"
      },
      {
        "name": "Sant Cugat del Vallès",
        "data": { "...": "..." },
        "narrative": "…"
      }
    ],
    "model": {
      "provider": "...",
      "model": "...",
      "usage": { }
    }
  }
}
```

Order of `locations` matches `WEATHER_LOCATIONS` order.

## Pipeline

1. Parse `WEATHER_LOCATIONS`.
2. For each location, `fetch_weather(lat, lon)` (reuse existing Open-Meteo helper).
3. One `model-router` `/v1/generate` call: prompt includes both named snapshots; ask for exactly two lines labeled with the location names (no preamble).
4. Parse narratives by matching location name prefixes / labels; if parse fails, set each `narrative` to a deterministic template from structured data (condition + temp) so the brief still succeeds.
5. Attach shared `model` metadata from the single generate response (or omit usage fields on template fallback).

## Consumers to update

- `scripts/generate-daily-brief.sh` — assert two locations by name and non-empty narratives.
- Paperclip Routine description (via `ensure-daily-brief-routine`) — instruct Hermes to comment weather for **both** cities (condition/temp + narrative each).
- README / `.env.example` — document `WEATHER_LOCATIONS`.

## Out of scope

- Per-request location overrides
- Geocoding by place name at runtime
- Forecast beyond current conditions
- Changing Decider routing or non-weather brief sections

## Acceptance

- Default config yields Barcelona + Sant Cugat in `locations` with distinct Open-Meteo `data`.
- Exactly one model-router generate call per brief for weather narratives (when the model is reachable).
- Host smoke `./scripts/generate-daily-brief.sh` passes.
- Hermes daily-brief comment includes both cities after routine description update.
