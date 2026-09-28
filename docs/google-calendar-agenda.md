# Google Calendar agenda — operator guide

The daily brief **`sections.agenda`** lists events from your Google Calendar for **today + tomorrow** (`Europe/Madrid`). Fetching runs inside **`personal-assistant`**; Hermes only formats the JSON. Without OAuth env vars the brief still succeeds with `sections.agenda_status: "unconfigured"`.

Secrets live only in the **host `.env`** (gitignored). Never commit tokens or paste them into Paperclip issues, Telegram, or chat logs.

## Prerequisites

- Helm repo cloned; `personal-assistant` service defined in `compose.yaml`
- Python 3 on the host (stdlib only — no extra packages for the OAuth script)
- A Google account with the calendars you want in the brief

## 1. Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a **project** (e.g. `helm-daily-brief`).
3. **APIs & Services → Library** → enable **Google Calendar API**.

## 2. OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** (or Internal if Workspace-only).
3. App name, support email, developer contact — fill required fields.
4. **Scopes → Add or remove scopes** → add **`…/auth/calendar.readonly`** (Calendar API read-only).
5. **Test users**: add your Google account while the app is in **Testing** (or publish when ready).

## 3. OAuth client (desktop / loopback)

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app** (recommended) or **Web application**.
3. If **Web application**, under **Authorized redirect URIs** add:
   - `http://127.0.0.1:8765/`
4. Create → copy **Client ID** and **Client secret** once. Store them only in host `.env`.

## 4. Host `.env` (client id + secret)

In the repo root (same file as `BETTER_AUTH_SECRET`):

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
# GOOGLE_REFRESH_TOKEN=   ← filled in step 5
# GOOGLE_CALENDAR_IDS=primary
```

Do **not** commit `.env`.

## 5. Refresh token (one-shot script)

From repo root, with client id/secret exported or already in `.env`:

```bash
set -a && source .env && set +a
python3 scripts/google-calendar-oauth.py
```

The script opens a browser (or use `--no-browser` and open the printed URL). Sign in, approve **read-only Calendar** access. On success it prints the **refresh token on stdout** (instructions on stderr).

Append to `.env`:

```bash
GOOGLE_REFRESH_TOKEN=<paste-token-from-script-output>
```

If you see “No refresh_token”, revoke the app under [Google Account → Third-party access](https://myaccount.google.com/permissions) and run the script again.

## 6. Calendar IDs (`GOOGLE_CALENDAR_IDS`)

Comma-separated list passed to `personal-assistant`. Default when unset: **`primary`** (your main calendar).

| Source | How to get the ID |
|--------|-------------------|
| Primary | Use `primary` |
| Other calendars | Google Calendar → **Settings** → select calendar → **Integrate calendar** → **Calendar ID** (often `name@group.calendar.google.com`) |

Example:

```bash
GOOGLE_CALENDAR_IDS=primary,abc123@group.calendar.google.com
```

## 7. Apply and smoke

Restart so Compose injects the new env into the container:

```bash
newgrp docker <<'EOF'
cd /path/to/helm
docker compose up -d personal-assistant
EOF
```

Host-side brief (no Paperclip):

```bash
./scripts/generate-daily-brief.sh
```

Expect `sections.agenda_status` **`ok`** when creds are valid (empty `agenda` is fine if you have no events). **`error`** means fix OAuth or API access; the rest of the brief still returns.

## Variable reference

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | OAuth client id |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REFRESH_TOKEN` | Long-lived refresh token from the script |
| `GOOGLE_CALENDAR_IDS` | Comma-separated calendar IDs; default `primary` |

Key names are also documented (comment-only) in [`.env.example`](../.env.example). Telegram and Paperclip setup: [telegram-daily-brief.md](telegram-daily-brief.md).
