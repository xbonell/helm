# Daily Brief Telegram DM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each Paperclip Daily brief run, Hermes DMs the user on Telegram with the same summary as the issue comment, including weather condition emojis.

**Architecture:** Add `emoji` per location in `personal-assistant` JSON (fixed condition→emoji map). Extend the Routine DESCRIPTION so Hermes comments on Paperclip, then `send_message` to the Telegram home DM, then marks done. Operator pairs a BotFather bot into `data/hermes/.env`; no second scheduler.

**Tech Stack:** Hermes gateway Telegram platform, Paperclip Routine, personal-assistant Python, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-27-daily-brief-telegram-design.md`

## Global Constraints

- Destination: private DM with the bot only (not group/channel)
- Paperclip issue comment + done remain; Telegram is additive
- Message body matches issue summary: date, route, both cities’ weather, priorities
- Emoji from fixed map on structured `condition` — not LLM-invented
- Prefer `emoji` field on each `sections.weather.locations[]` entry from personal-assistant
- Telegram failure: comment a warning on the issue; still mark done if brief + Paperclip comment succeeded
- Secrets only in `data/hermes/.env` (gitignored); document keys in `.env.example` / docs without real tokens
- Prefer TDD; only commit when the user explicitly asks

---

## File map

| File | Responsibility |
|------|----------------|
| `services/personal-assistant/weather_emoji.py` | `condition` → emoji mapper |
| `services/personal-assistant/test_weather_emoji.py` | Mapper unit tests |
| `services/personal-assistant/brief.py` | Attach `emoji` on each location |
| `services/personal-assistant/Dockerfile` | COPY new module if needed |
| `scripts/lib/ensure-daily-brief-routine.cjs` | DESCRIPTION: Telegram send step + emoji lines |
| `docs/telegram-daily-brief.md` | Operator bot setup + pairing guide |
| `README.md` / `docs/development.md` / `.env.example` | Point at guide; list `TELEGRAM_*` names |
| `scripts/smoke-telegram-brief.sh` (optional) | Documented curl + reminder to check Telegram after manual routine run |

---

### Task 0: Operator bot setup (manual — guide the human)

**Files:**
- Create: `docs/telegram-daily-brief.md` (write this file in Task 4; **execute these steps with the human before/during Task 3 smoke**)

This task is the human checklist. The implementer writes the doc in Task 4; the controller (or human) performs pairing.

#### Step-by-step: create the bot

1. Open Telegram; message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Choose a **display name** (e.g. `Helm Daily Brief`).
4. Choose a **username** ending in `bot` (e.g. `helm_xbonell_brief_bot`).
5. BotFather replies with a token like `123456:ABC-DEF...`. **Copy it once**; treat as a secret.
6. Optional: `/setdescription` and `/setprivacy` — for a DM-only personal bot, Privacy Mode on is fine.

#### Step-by-step: get your numeric user id

1. Message [@userinfobot](https://t.me/userinfobot) (or [@getidsbot](https://t.me/getidsbot)).
2. Note the **Id** number (e.g. `123456789`). This is `TELEGRAM_ALLOWED_USERS`.

#### Step-by-step: wire Helm Hermes

1. On the host (repo root), ensure Hermes is running: `docker compose ps hermes`.
2. Append to Hermes profile env **inside the volume** (do not commit):

```bash
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose exec -T -u hermes hermes sh -c '
  ENV=/opt/data/.env
  grep -vE "^(TELEGRAM_BOT_TOKEN|TELEGRAM_ALLOWED_USERS|TELEGRAM_HOME_CHANNEL)=" "$ENV" > /tmp/h.env || true
  printf "%s\n" \
    "TELEGRAM_BOT_TOKEN=<PASTE_TOKEN>" \
    "TELEGRAM_ALLOWED_USERS=<PASTE_USER_ID>" \
    >> /tmp/h.env
  mv /tmp/h.env "$ENV"
  chmod 600 "$ENV"
  grep -E "^TELEGRAM_" "$ENV" | cut -d= -f1
'
docker compose restart hermes
EOF
```

Replace placeholders before running (never paste the real token into git, issues, or chat logs).

3. Wait until the gateway is up (`docker compose logs hermes --tail 30`).

#### Step-by-step: open the DM and set home

1. In Telegram, search for your bot username → **Start** / send `/start`.
2. Set Hermes home channel to this DM so `send_message` without an explicit target reaches you:
   - Prefer Hermes docs’ `/sethome` in that chat if the gateway exposes it, **or**
   - Set `TELEGRAM_HOME_CHANNEL=<your_user_id>` (same numeric id often works for DMs) in `/opt/data/.env` and restart Hermes again.
3. Confirm Hermes logs show Telegram platform connected (no auth errors).

#### Smoke pairing (before code changes optional)

If Hermes CLI inside the container supports it:

```bash
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose exec -T hermes hermes send --help || true
EOF
```

Otherwise wait for Task 3 routine smoke: after implementation, run `./scripts/run-daily-brief-routine.sh` and expect a DM.

- [ ] **Human:** Bot created, token + user id in `data/hermes/.env`, `/start` sent, Hermes restarted, home channel set.

---

### Task 1: Weather emoji mapper + brief field

**Files:**
- Create: `services/personal-assistant/weather_emoji.py`
- Create: `services/personal-assistant/test_weather_emoji.py`
- Modify: `services/personal-assistant/brief.py` (add `"emoji": emoji_for_condition(snapshot.condition)` on each location)
- Modify: `services/personal-assistant/Dockerfile` — ensure `weather_emoji.py` is COPYed
- Modify: `services/personal-assistant/test_brief_weather.py` — assert `emoji` present when building locations (if tests construct full brief with mocks)

**Interfaces:**
- Produces: `emoji_for_condition(condition: str) -> str`
- Produces: each `sections.weather.locations[]` item includes `emoji: str`

- [ ] **Step 1: Write failing tests**

```python
# services/personal-assistant/test_weather_emoji.py
from weather_emoji import emoji_for_condition

def test_known_conditions():
    assert emoji_for_condition("clear") == "☀️"
    assert emoji_for_condition("overcast") == "☁️"
    assert emoji_for_condition("rain") == "🌧️"
    assert emoji_for_condition("thunderstorm") == "⛈️"

def test_unknown_falls_back():
    assert emoji_for_condition("code-999") == "🌤️"
    assert emoji_for_condition("") == "🌤️"
```

Map at least every key in `weather.py` `_WMO` values:

| condition | emoji |
|-----------|--------|
| clear | ☀️ |
| mainly clear | 🌤️ |
| partly cloudy | ⛅ |
| overcast | ☁️ |
| fog / depositing rime fog | 🌫️ |
| light drizzle | 🌦️ |
| light rain / rain / heavy rain / rain showers | 🌧️ |
| light snow | 🌨️ |
| thunderstorm | ⛈️ |
| (default) | 🌤️ |

- [ ] **Step 2: Run tests — expect fail**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_weather_emoji.py -v
```

Expected: import failure

- [ ] **Step 3: Implement mapper + wire brief**

```python
# services/personal-assistant/weather_emoji.py
from __future__ import annotations

_EMOJI = {
    "clear": "☀️",
    "mainly clear": "🌤️",
    "partly cloudy": "⛅",
    "overcast": "☁️",
    "fog": "🌫️",
    "depositing rime fog": "🌫️",
    "light drizzle": "🌦️",
    "light rain": "🌧️",
    "rain": "🌧️",
    "heavy rain": "🌧️",
    "light snow": "🌨️",
    "rain showers": "🌧️",
    "thunderstorm": "⛈️",
}

def emoji_for_condition(condition: str) -> str:
    key = (condition or "").strip().lower()
    return _EMOJI.get(key, "🌤️")
```

In `brief.py` location dict:

```python
"emoji": emoji_for_condition(snapshot.condition),
```

- [ ] **Step 4: Run tests — expect pass; rebuild PA**

```bash
cd services/personal-assistant && uv run --with pytest --with httpx pytest test_weather_emoji.py test_brief_weather.py test_locations.py test_weather.py -v
newgrp docker <<'EOF'
cd /home/xbonell/Developer/00.personal/helm
docker compose up -d --build personal-assistant
EOF
curl -fsS http://127.0.0.1:8083/v1/generate-daily-brief -H 'content-type: application/json' -d '{}' \
  | python3 -c "import json,sys; b=json.load(sys.stdin); print([(x['name'], x.get('emoji'), x['data']['condition']) for x in b['sections']['weather']['locations']])"
```

Expected: both cities print an emoji

- [ ] **Step 5: Commit only if user asks**

---

### Task 2: Update Routine DESCRIPTION for Telegram + emoji

**Files:**
- Modify: `scripts/lib/ensure-daily-brief-routine.cjs` (`DESCRIPTION` constant)

**Interfaces:**
- Consumes: brief JSON with `locations[].emoji`
- Produces: Hermes instructions that comment + Telegram DM + done

- [ ] **Step 1: Replace DESCRIPTION steps** with this exact behavior (adapt escaping for the JS template literal):

```
Generate the Helm personal-assistant daily brief.

Steps (do these exactly):
1. Use the terminal tool (not execute_code) to run:
   curl -sS -m 60 -X POST http://personal-assistant:8083/v1/generate-daily-brief -H 'Content-Type: application/json' -d '{}'
2. Build a short summary from the JSON:
   - date, Decider route (routing.choice)
   - for each sections.weather.locations entry: "{emoji} {name}: {condition}, {temp}°C" plus narrative
   - priorities list
3. Comment that summary on this Paperclip issue.
4. Send the same summary to the user on Telegram via the send_message tool (target the Telegram home DM / configured home channel). Do not invent chat ids if home is set.
5. Mark this issue done via Paperclip API using $PAPERCLIP_API_KEY (same PATCH pattern as today).
6. If Telegram send fails after a successful brief + comment: add a short warning comment, then still mark done.

Do not invent a parallel brief. Do not use execute_code.
```

- [ ] **Step 2: Re-ensure routine**

```bash
./scripts/ensure-daily-brief-routine.sh
```

Expected: `using_routine` / patch OK; DB description contains `send_message` / Telegram

- [ ] **Step 3: Commit only if user asks**

---

### Task 3: End-to-end smoke (Paperclip + Telegram DM)

**Files:** none required (optional note in report)

**Prerequisites:** Task 0 pairing complete; Tasks 1–2 done; Hermes has `TELEGRAM_*` and `PAPERCLIP_API_KEY`.

- [ ] **Step 1: Manual routine run**

```bash
./scripts/run-daily-brief-routine.sh
```

Expected:
- Heartbeat `succeeded`
- Issue `done`
- Issue comments include emoji weather lines
- **Telegram DM** received with the same summary

- [ ] **Step 2: If no DM** — debug checklist:
  - Hermes logs for Telegram / send_message errors
  - `TELEGRAM_ALLOWED_USERS` matches the account that `/start`ed the bot
  - Home channel set; try explicit `telegram:<user_id>` once in a one-off Hermes instruction
  - Bot not blocked by user

- [ ] **Step 3: Record smoke evidence** in the implementer report (issue id, whether DM arrived — do not paste tokens)

---

### Task 4: Docs — operator guide + README pointers

**Files:**
- Create: `docs/telegram-daily-brief.md` — paste/adapt **Task 0** checklist (BotFather, user id, `.env` keys, `/start`, home channel, smoke commands)
- Modify: `README.md` Daily brief section — one paragraph + link to that doc
- Modify: `docs/development.md` — link under Paperclip daily brief routine
- Modify: `.env.example` — comment-only block listing Hermes Telegram keys (values empty; note “set in data/hermes/.env”):

```bash
# Hermes Telegram (set in data/hermes/.env — not root .env)
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_ALLOWED_USERS=
# TELEGRAM_HOME_CHANNEL=
```

- [ ] **Step 1: Write `docs/telegram-daily-brief.md`**
- [ ] **Step 2: Link from README + development.md**
- [ ] **Step 3: Update `.env.example` comments**
- [ ] **Step 4: Commit only if user asks**

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Bot setup guide | 0, 4 |
| DM-only delivery | 0, 2, 3 |
| Keep Paperclip comment + done | 2, 3 |
| Same summary content | 2 |
| Condition→emoji map | 1 |
| Hermes send_message in routine | 2 |
| Telegram fail → warn, still done | 2 |
| Docs / no committed secrets | 4 |

## Placeholder / consistency check

- Emoji table covers all `_WMO` condition strings in `weather.py`
- DESCRIPTION still uses curl to PA + Paperclip PATCH with env key
- No second cron/systemd scheduler introduced
