# Daily brief → Telegram DM (design)

**Date:** 2026-09-27  
**Status:** approved in chat; awaiting spec file review before implementation plan

## Goal

Deliver the existing morning daily brief to the user as a **Telegram private DM**, in addition to the Paperclip issue comment, with **weather condition emojis** on each city line.

## Context

- Paperclip Routine **Daily brief** already runs at `0 7 * * *` Europe/Madrid, wakes **Hermes Runtime**, which calls `personal-assistant` and comments on the issue.
- Hermes supports Telegram via a **BotFather bot** (`TELEGRAM_BOT_TOKEN`, allowlist, home channel / `send_message`).
- Email/Telegram delivery was previously out of scope for the routine; this extends that path.

## Decisions

| Topic | Choice |
|--------|--------|
| Destination | Private DM with the bot (not a group/channel) |
| Paperclip | Keep issue comment + done; Telegram is additive |
| Message body | Same summary as the issue comment (date, route, both cities weather, priorities) |
| Emoji | Yes — map structured `condition` → emoji on Telegram (and optionally the same on the issue comment for consistency) |
| Integration | Hermes sends via Telegram platform during the routine (`send_message` / home DM) |

## Bot required?

**Yes.** Hermes Telegram integration uses the Bot API only. Setup (operator guide in the plan):

1. Create a bot with [@BotFather](https://t.me/BotFather) → copy token.  
2. Get your numeric Telegram user id (e.g. [@userinfobot](https://t.me/userinfobot)).  
3. Put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS=<your_id>` in `data/hermes/.env`.  
4. Open a DM with the bot (`/start`).  
5. Set Hermes home channel to that DM (gateway `/sethome` or `TELEGRAM_HOME_CHANNEL` / documented equivalent).  
6. Restart Hermes gateway; smoke with a one-off send.

Exact env key names and Helm file edits land in the implementation plan / setup guide.

## Runtime flow

```
07:00 Europe/Madrid
  → Paperclip Routine creates issue, wakes Hermes
  → Hermes POST personal-assistant /v1/generate-daily-brief
  → Hermes comments summary on the Paperclip issue
  → Hermes formats Telegram text (emoji weather lines) and DMs the user
  → Hermes marks issue done
```

If Telegram send fails: leave a short issue comment noting the failure; still prefer marking done only if the brief itself succeeded (or leave `blocked` with reason — plan will pick one explicit rule). **Recommendation:** brief + Paperclip comment success is enough to mark done; Telegram failure is logged/commented as a warning so a transient Telegram outage does not strand the routine.

## Message format (Telegram)

Plain text (or Telegram Markdown if Hermes defaults to it), roughly:

```
Daily brief — {date}
Route: {routing.choice}

Weather
{emoji} {city}: {condition}, {temp}°C
  {narrative}
… (one block per locations[])

Priorities
- …
```

Emoji mapping is a **fixed table** from Open-Meteo `condition` strings already on the brief (e.g. `clear` → ☀️, `overcast` → ☁️, `rain` → 🌧️, `thunderstorm` → ⛈️, default → 🌤️). Do **not** rely on the LLM to invent emoji.

Implementation options (plan picks one):

- **A (preferred):** small mapper in `personal-assistant` that adds `emoji` per location in the JSON; Hermes just prints it.  
- **B:** mapper only in Hermes routine instructions / a tiny script Hermes runs.

Prefer **A** so Telegram and Paperclip stay consistent and tests cover the map.

## Helm / config changes (expected)

- Document `TELEGRAM_*` in `.env.example` / README / development (secrets stay in `data/hermes/.env`, never committed).  
- Update Daily brief Routine `DESCRIPTION` with the Telegram send step + emoji-aware summary.  
- Optional smoke: script or documented manual “send test DM” after bot pairing.  
- No second scheduler; Paperclip remains the clock.

## Out of scope

- Group/channel delivery  
- Telegram webhooks / local Bot API server  
- Replacing Paperclip Routines  
- Interactive Q&A bot beyond delivery (can exist later via Hermes gateway chat)  
- Email or other channels  

## Acceptance

- After bot setup + pairing, a manual routine run posts the Paperclip comment **and** a DM with emoji weather lines for Barcelona and Sant Cugat.  
- Scheduled 07:00 run does the same without host systemd.  
- Missing/invalid Telegram config fails the send step clearly without deleting the Paperclip audit trail.
