# Telegram daily brief — operator guide

After each **Daily brief** Paperclip run, Hermes sends the same summary as the issue comment to your **private Telegram DM** (weather emojis included). Paperclip comment + mark done are unchanged; Telegram is additive.

Secrets live only in **`data/hermes/.env`** on the host (gitignored). Inside the Hermes container that file is **`/opt/data/.env`**. Never commit tokens or paste them into issues or chat logs.

## Prerequisites

- Hermes running: `docker compose ps hermes`
- `PAPERCLIP_API_KEY` already in `data/hermes/.env` (see `./scripts/ensure-hermes-paperclip-key.sh`)
- Daily brief routine installed: `./scripts/ensure-daily-brief-routine.sh`

## 1. Create the bot (BotFather)

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Choose a **display name** (e.g. `Helm Daily Brief`).
4. Choose a **username** ending in `bot` (e.g. `helm_xbonell_brief_bot`).
5. BotFather replies with a token like `123456:ABC-DEF...`. **Copy it once**; treat it as a secret.
6. Optional: `/setdescription` and `/setprivacy` — for a DM-only personal bot, Privacy Mode on is fine.

## 2. Get your numeric user id

1. Message [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot).
2. Note the **Id** number (e.g. `123456789`). This value is **`TELEGRAM_ALLOWED_USERS`**.

## 3. Wire Hermes (`data/hermes/.env`)

On the host (repo root), append Telegram keys **inside the Hermes volume** (do not commit):

```bash
newgrp docker <<'EOF'
cd /path/to/helm
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

Replace `<PASTE_TOKEN>` and `<PASTE_USER_ID>` before running. Key names are also listed (comment-only) in the repo root [`.env.example`](../.env.example).

Wait until the gateway is up: `docker compose logs hermes --tail 30`.

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated Telegram user ids allowed to talk to the bot |
| `TELEGRAM_HOME_CHANNEL` | Optional; numeric user id for DM home (see below) |

## 4. Open the DM and set home channel

1. In Telegram, search for your bot username → **Start** / send `/start`.
2. Set Hermes **home channel** so `send_message` without an explicit target reaches you:
   - Prefer Hermes `/sethome` in that chat if the gateway exposes it, **or**
   - Set `TELEGRAM_HOME_CHANNEL=<your_user_id>` (same numeric id often works for DMs) in `/opt/data/.env` and restart Hermes again.
3. Confirm Hermes logs show the Telegram platform connected (no auth errors).

## 5. Smoke pairing (optional, before routine)

If Hermes CLI inside the container supports it:

```bash
newgrp docker <<'EOF'
cd /path/to/helm
docker compose exec -T hermes hermes send --help || true
EOF
```

Otherwise skip to end-to-end smoke below.

## 6. End-to-end smoke (Paperclip + DM)

```bash
./scripts/run-daily-brief-routine.sh
```

Expected:

- Heartbeat **succeeded**
- Issue **done**
- Issue comments include **Weather** lines (now / rest-of-today / tomorrow per city), a **Narrative** block (`sections.weather.narrative`), then an **Agenda** block (`sections.agenda` / `sections.agenda_status` — event lines or “No events”; short warning if unconfigured or error)
- **Telegram DM** with the same summary

Host-only brief (no Paperclip, no Telegram send): `./scripts/generate-daily-brief.sh`.

## Troubleshooting (no DM)

- Check Hermes logs for Telegram / `send_message` errors.
- `TELEGRAM_ALLOWED_USERS` must match the account that sent `/start`.
- Home channel set; try explicit `telegram:<user_id>` once in a one-off Hermes instruction.
- Ensure the bot is not blocked by the user.

## Human checklist

- [ ] Bot created; token + user id in `data/hermes/.env`
- [ ] `/start` sent in DM
- [ ] Hermes restarted; home channel set
- [ ] `./scripts/run-daily-brief-routine.sh` → DM received
