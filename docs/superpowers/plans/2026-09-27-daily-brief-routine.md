# Daily Brief Paperclip Routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Schedule Helm’s existing daily brief via a Paperclip Routine at 07:00 Europe/Madrid assigned to Hermes Runtime.

**Architecture:** Paperclip schedule trigger creates an issue and wakes Hermes; Hermes calls `personal-assistant:8083/v1/generate-daily-brief`, comments the result, marks done. No systemd.

**Tech Stack:** Paperclip board API, Hermes gateway agent, existing `scripts/generate-daily-brief.sh` for host smoke.

**Spec:** `docs/superpowers/specs/2026-09-27-daily-brief-routine-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/ensure-daily-brief-routine.sh` | Idempotent create/update of PA project + routine + cron trigger via board API |
| `README.md` / `docs/development.md` | Document schedule + how to pause / manual run |

---

### Task 1: Ensure routine via script + live Paperclip

**Steps:**

- [x] Create board API key (or reuse pattern from prior smokes) inside script using Paperclip DB hash insert **or** document UI path; prefer scripted API create of project/routine/trigger.
- [x] Create project “Personal Assistant” if missing.
- [x] Create/update routine “Daily brief” assigned to Hermes Runtime with description instructing Hermes to POST `http://personal-assistant:8083/v1/generate-daily-brief`, comment summary, mark done.
- [x] Add schedule trigger `0 7 * * *` / `Europe/Madrid` if missing.
- [x] Confirm Hermes `wakeOnDemand` is true.
- [x] Manually run routine once; wait for Hermes run success and issue disposition.
- [x] Update README + development.md with schedule notes.
- [ ] Commit docs + script (no secrets).
