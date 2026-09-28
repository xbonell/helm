# Google Calendar Agenda Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `sections.agenda` from Google Calendar (today + tomorrow, Europe/Madrid) for the daily brief Paperclip comment and Telegram DM.

**Architecture:** personal-assistant refreshes an OAuth token and lists events via Calendar API REST (`httpx`); normalizes to agenda items; Hermes only formats the JSON. Missing/failed calendar never fails the brief.

**Tech Stack:** Google Calendar API v3 + OAuth refresh, httpx, pytest, Compose env, Paperclip Routine DESCRIPTION.

**Spec:** `docs/superpowers/specs/2026-09-28-google-calendar-agenda-design.md`

## Global Constraints

- Horizon: **today + tomorrow** only (`Europe/Madrid`)
- Calendars: IDs from `GOOGLE_CALENDAR_IDS` (default `primary` when OAuth present)
- Auth: refresh token env vars; readonly scope; secrets never in git, comments, or Telegram
- Brief must succeed with `agenda_status` `unconfigured` / `error` / `ok`
- Prefer TDD; commit only when the user asks
- No new heavy Google client libs — use `httpx` REST (same as weather)

---

## File map

| File | Responsibility |
|------|----------------|
| `services/personal-assistant/gcal.py` | OAuth refresh, list events, normalize, status |
| `services/personal-assistant/test_calendar.py` | Fixture-based parser + status tests |
| `services/personal-assistant/brief.py` | Wire `fetch_agenda` into `sections.agenda` |
| `services/personal-assistant/test_brief_agenda.py` | Brief assembly with mocked calendar |
| `services/personal-assistant/Dockerfile` | COPY `calendar.py` |
| `compose.yaml` / `.env.example` | Pass through Google env vars (commented in example) |
| `scripts/google-calendar-oauth.py` | One-shot local consent → print refresh token |
| `docs/google-calendar-agenda.md` | Operator setup |
| `scripts/generate-daily-brief.sh` | Smoke asserts |
| `scripts/lib/ensure-daily-brief-routine.cjs` | Agenda lines in DESCRIPTION |

---

### Task 1: Calendar normalize + fetch

**Files:**
- Create: `services/personal-assistant/calendar.py`
- Create: `services/personal-assistant/test_calendar.py`

**Interfaces:**
- Produces: `fetch_agenda(*, now: datetime | None = None, client: httpx.Client | None = None) -> AgendaResult`
- `AgendaResult` dataclass: `items: list[AgendaItem]`, `status: Literal["ok","unconfigured","error"]`, `error: str | None`
- `AgendaItem.as_dict()` → keys: `date`, `time`, `end_time`, `title`, `all_day`, `calendar`
- Consumes env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_IDS`

- [ ] **Step 1: Write failing tests** with a frozen Calendar API events list fixture

```python
# test_calendar.py — assert normalize_events:
# - timed event → HH:MM Madrid, all_day False
# - all-day → time "all-day", all_day True
# - window today+tomorrow only (drop day+2)
# - merge two calendars, dedupe by id
# - fetch_agenda with missing env → status unconfigured, items []
# - fetch_agenda with mocked 401 on token → status error, items []
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_calendar.py -v
```

Expected: FAIL (module/import missing)

- [ ] **Step 3: Implement `calendar.py`**

Core pieces:

```python
BRIEF_TZ = ZoneInfo("Europe/Madrid")
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

@dataclass
class AgendaItem:
    date: str
    time: str
    end_time: str | None
    title: str
    all_day: bool
    calendar: str
    event_id: str = ""

    def as_dict(self) -> dict: ...

@dataclass
class AgendaResult:
    items: list[AgendaItem]
    status: str  # ok | unconfigured | error
    error: str | None = None

def madrid_window(now: datetime) -> tuple[datetime, datetime]:
    """[start of today, start of day-after-tomorrow) in Madrid."""
    ...

def normalize_events(raw_items: list[dict], *, calendar_id: str, window: tuple[datetime, datetime]) -> list[AgendaItem]:
    ...

def fetch_agenda(*, now: datetime | None = None, client: httpx.Client | None = None) -> AgendaResult:
    # missing creds → unconfigured
    # POST token, GET events per calendar_id, merge, sort (date, all-day first, time), dedupe event_id
    ...
```

Token body: `grant_type=refresh_token` + client id/secret + refresh token.  
Events query: `singleEvents=true`, `orderBy=startTime`, `timeMin`/`timeMax` RFC3339 with offset.

- [ ] **Step 4: Tests pass**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_calendar.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit only if user asks**

---

### Task 2: Brief assembly + PA image

**Files:**
- Modify: `services/personal-assistant/brief.py`
- Create: `services/personal-assistant/test_brief_agenda.py`
- Modify: `services/personal-assistant/Dockerfile` (COPY `calendar.py`)

**Interfaces:**
- Consumes: `fetch_agenda` → `AgendaResult`
- Produces: `sections.agenda` as list of `as_dict()` (without `event_id` in public dict — omit internal id from `as_dict`), `sections.agenda_status`, optional `sections.agenda_error`

- [ ] **Step 1: Failing tests**

```python
def test_generate_daily_brief_uses_calendar_agenda(monkeypatch):
    # mock fetch_agenda → ok with two items
    # mock weather/route/narrative as existing brief tests do
    # assert sections.agenda == [...], agenda_status == "ok"
    # assert mock agenda times not present

def test_generate_daily_brief_calendar_unconfigured(monkeypatch):
    # fetch_agenda → unconfigured
    # assert agenda == [], agenda_status == "unconfigured"
```

- [ ] **Step 2: Implement wiring**

In `generate_daily_brief`, replace `mocked["agenda"]` with:

```python
agenda_result = fetch_agenda()
sections_agenda = [item.as_dict() for item in agenda_result.items]
# keep priorities/fitness/news from mock_context()
# set agenda_status / agenda_error on sections
```

Update Dockerfile COPY line to include `calendar.py`.

- [ ] **Step 3: Full PA unit suite**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_calendar.py test_brief_agenda.py test_brief_weather.py test_weather.py test_weather_emoji.py test_locations.py -v
```

Expected: all PASS

- [ ] **Step 4: Rebuild PA**

```bash
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose up -d --build personal-assistant
EOF
```

- [ ] **Step 5: Commit only if user asks**

---

### Task 3: Operator OAuth + Compose env + docs

**Files:**
- Create: `scripts/google-calendar-oauth.py`
- Create: `docs/google-calendar-agenda.md`
- Modify: `compose.yaml` (personal-assistant environment)
- Modify: `.env.example` (commented key names only)
- Modify: `README.md` (one paragraph + link to doc)

**Interfaces:**
- OAuth script reads client id/secret from env or flags; prints refresh token once to stdout; never writes secrets into the repo
- Compose passes `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_IDS` from host `.env`

- [ ] **Step 1: OAuth helper script**

Desktop/installed-app flow (or loopback): scope `https://www.googleapis.com/auth/calendar.readonly`. Document: create OAuth client in Google Cloud Console, enable Calendar API, run script, paste refresh token into host `.env`.

- [ ] **Step 2: Compose + `.env.example`**

```yaml
# compose personal-assistant environment (add):
GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID:-}
GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET:-}
GOOGLE_REFRESH_TOKEN: ${GOOGLE_REFRESH_TOKEN:-}
GOOGLE_CALENDAR_IDS: ${GOOGLE_CALENDAR_IDS:-primary}
```

`.env.example` comments only — no real tokens.

- [ ] **Step 3: Operator doc** — BotFather-style checklist for Google Cloud + script + `GOOGLE_CALENDAR_IDS` how to find calendar IDs.

- [ ] **Step 4: Commit only if user asks**

---

### Task 4: Smoke + Hermes / Telegram copy

**Files:**
- Modify: `scripts/generate-daily-brief.sh`
- Modify: `scripts/lib/ensure-daily-brief-routine.cjs`
- Modify: `docs/telegram-daily-brief.md` (brief note that Agenda block follows Narrative)

**Summary format for Hermes/Telegram:**

```
Agenda
- {date} {time} {title}
…
```

If empty and status ok: `Agenda\n- No events`  
If `unconfigured` / `error`: one short warning line (no secrets).

- [ ] **Step 1: Update smoke asserts** — `agenda` is a list; `agenda_status` in `{ok,unconfigured,error}`; print agenda lines

- [ ] **Step 2: Update DESCRIPTION**; re-ensure routine

```bash
./scripts/ensure-daily-brief-routine.sh
```

- [ ] **Step 3: `./scripts/generate-daily-brief.sh`** passes (with or without live Google creds)

- [ ] **Step 4: Optional** with live creds set — confirm real events in smoke output / Telegram via Bot API or routine run

- [ ] **Step 5: Commit only if user asks**

---

## Spec coverage

| Spec | Task |
|------|------|
| today + tomorrow Madrid | 1 |
| primary + named IDs | 1, 3 |
| OAuth refresh | 1, 3 |
| PA ownership | 1–2 |
| agenda shape + status | 1–2 |
| Hermes/Telegram Agenda | 4 |
| Fail-soft | 1–2 |
| Operator setup | 3 |

## Consistency

- Fitness / news / priorities remain mocked
- No secrets in repo
- Dockerfile must COPY `calendar.py` or container import fails
