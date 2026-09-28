# Google Calendar → daily brief agenda (design)

**Date:** 2026-09-28  
**Status:** approved in chat; awaiting spec file review before implementation

## Goal

Replace mocked `sections.agenda` with real events from the operator’s Google Calendar (`xbonell@gmail.com`), covering **today + tomorrow** in `Europe/Madrid`, for Paperclip comments and Telegram DMs.

## Context

- Daily brief already ships live dual-city day-ahead weather + shared narrative.
- `mock_context()` still supplies agenda, fitness, news, and priorities.
- Secrets pattern: gitignored env (Hermes `.env` / Compose); names documented in `.env.example` comments only.

## Decisions

| Topic | Choice |
|--------|--------|
| Horizon | **Today + tomorrow** (`Europe/Madrid`) |
| Calendars | **Primary + named extras** via env calendar IDs |
| Auth | OAuth **refresh token** (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`) |
| Ownership | Fetch inside **personal-assistant** (same pattern as Open-Meteo) |
| Hermes | Formats `sections.agenda` only; no Google API calls |

## Architecture

1. New `calendar.py` in personal-assistant: refresh access token → list events for each configured calendar ID → normalize.
2. `generate_daily_brief` fills `sections.agenda` from that module; fitness / news / priorities stay mocked.
3. Hermes Daily brief DESCRIPTION adds an **Agenda** block (time + title lines).
4. Operator one-shot OAuth consent (script or doc) produces the refresh token; never commit or paste into issues/Telegram.

## Response shape

```json
"sections": {
  "agenda": [
    {
      "date": "2026-09-29",
      "time": "09:30",
      "end_time": "10:30",
      "title": "Focus block",
      "all_day": false,
      "calendar": "primary"
    },
    {
      "date": "2026-09-29",
      "time": "all-day",
      "end_time": null,
      "title": "Public holiday",
      "all_day": true,
      "calendar": "primary"
    }
  ],
  "agenda_status": "ok"
}
```

- Timed events: `time` / `end_time` as `HH:MM` in Madrid.
- All-day: `all_day: true`, `time: "all-day"`, `end_time` null.
- Sort by `date`, then start (all-day before timed on the same day, or after — pick **all-day first**).
- Empty window → `agenda: []`, `agenda_status: "ok"`.

### Status / errors

| Condition | `agenda` | `agenda_status` | Extra |
|-----------|----------|-----------------|--------|
| Creds missing | `[]` | `unconfigured` | — |
| API / auth failure | `[]` | `error` | `agenda_error`: short safe string (no tokens) |
| Success (incl. empty) | list | `ok` | — |

Brief generation **must not fail** solely because calendar is down; weather and other sections still return.

## Config

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | OAuth client id |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REFRESH_TOKEN` | Long-lived refresh token |
| `GOOGLE_CALENDAR_IDS` | Comma-separated calendar IDs, e.g. `primary,abc@group.calendar.google.com` |

Default if `GOOGLE_CALENDAR_IDS` unset but OAuth present: `primary` only.

Wire into Compose for `personal-assistant` (not Hermes). Document setup in `docs/` (operator guide) + `.env.example` key names only.

## Google Calendar API

- Scope: `https://www.googleapis.com/auth/calendar.readonly`
- Window: Madrid start of today → end of tomorrow (exclusive end of day-after-tomorrow 00:00 Madrid), query with `timeMin` / `timeMax` RFC3339.
- `singleEvents=true`, `orderBy=startTime` per calendar; merge + re-sort across calendars.
- Deduplicate by event `id` if the same event appears on multiple listed calendars.

## Consumers

- `scripts/generate-daily-brief.sh` — assert `agenda` is a list; if `agenda_status == "ok"` and live creds present, optional soft check; always reject crash.
- Hermes DESCRIPTION — Agenda section after weather narrative (or before priorities); Telegram same text.
- Unit tests: fixture event payloads → normalize window, multi-calendar, all-day, error/unconfigured paths.

## Out of scope

- Creating / editing events
- Free/busy UI, conference links as first-class fields
- Un-mocking fitness / news / priorities
- Service accounts / Workspace domain-wide delegation
- Multi-day beyond tomorrow

## Acceptance

- With valid OAuth env, live brief returns real today+tomorrow events from configured calendars.
- Without creds, brief still succeeds with `agenda_status: "unconfigured"`.
- Paperclip/Telegram summary includes Agenda lines (or “No events”).
- Unit tests cover normalization + status paths; secrets never logged or commented.
