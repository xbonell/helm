# Daily brief — Paperclip Routine (design)

**Date:** 2026-09-27  
**Status:** approved in chat; awaiting spec file review before implementation

## Goal

Run Helm’s existing `generate-daily-brief` pipeline every morning at **07:00 Europe/Madrid**, coordinated by **Paperclip Routines** (not host systemd/cron).

## Context

- Daily brief is served by Compose service `personal-assistant` at  
  `POST http://personal-assistant:8083/v1/generate-daily-brief` (from the Docker network)  
  / `http://127.0.0.1:8083/...` (from the host).
- Pipeline already uses Decider routing, Open-Meteo weather, and `model-router` (`gpt-4o-mini`).
- **Hermes Runtime** (`hermes_gateway`) is the working agent; CEO stays paused/idle.

## Approach

Create a Paperclip **Routine** assigned to **Hermes Runtime** with a **schedule** trigger:

| Field | Value |
|--------|--------|
| Title | Daily brief |
| Assignee | Hermes Runtime |
| Project | New or existing PA project (prefer dedicated “Personal Assistant”) |
| Trigger kind | `schedule` |
| Cron | `0 7 * * *` |
| Timezone | `Europe/Madrid` |
| Status | `active` |
| Concurrency | `coalesce_if_active` |
| Catch-up | `skip_missed` |

Each fire creates an issue and wakes Hermes. Hermes must:

1. `POST` `http://personal-assistant:8083/v1/generate-daily-brief` with `{}`.
2. Post a short summary (date, route, weather narrative, priorities) as an issue comment.
3. Optionally write full JSON under a workspace path if useful; not required for MVP.
4. Mark the issue **done** with a clear disposition (avoid leaving `blocked`).

Routine **description** / issue template will spell these steps out so Hermes does not invent a parallel brief.

## Non-goals (this change)

- Email / Telegram / chat delivery
- systemd / host crontab
- Enabling CEO heartbeats
- Changing personal-assistant API shape

## Success criteria

- Routine visible in Paperclip with schedule `0 7 * * *` / `Europe/Madrid`.
- Manual “Run routine” (or next 07:00) creates an issue, Hermes run **succeeds**, brief content appears on the issue, status ends **done**.
- Missed runs are skipped (`skip_missed`); overlapping fires coalesce.

## Implementation notes

- Use board API (or UI) to create project (if needed), routine, and schedule trigger.
- Ensure Hermes `wakeOnDemand` remains enabled (already true).
- Document in `README.md` / `docs/development.md` how to pause the routine and how to smoke-run it.
- Repo may add a small helper script to create/update the routine idempotently (optional); live state lives in Paperclip DB, not git.

## Alternatives considered

- **systemd user timer** — simpler host curl; bypasses Paperclip audit trail. Rejected for Helm.
- **Hermes-native cron only** — duplicates Paperclip scheduling; weaker company/issue tracking.
