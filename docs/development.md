# Development

## Prerequisites

- Docker Engine + Docker Compose v2
- ~16 GB free RAM recommended (Decider-2B on CPU is the heavy piece)
- `curl`, `openssl`, `bash`

## First-time setup

```bash
./scripts/bootstrap.sh
docker compose up -d
./scripts/healthcheck.sh
```

`bootstrap.sh` creates `.env` with random secrets and seeds `data/hermes/` so Hermes can start without the interactive setup wizard.

## Common commands

```bash
docker compose up -d          # start
docker compose down           # stop (keeps volumes / bind mounts)
docker compose logs -f        # all logs
docker compose logs -f hermes # one service
docker compose config         # validate compose files
./scripts/healthcheck.sh      # Paperclip / Hermes / Decider / Decision API
./scripts/backup.sh           # tar persistent state
```

## Validate compose without starting

```bash
# Requires BETTER_AUTH_SECRET and HERMES_API_SERVER_KEY in the environment or .env
set -a && source .env && set +a
docker compose config >/dev/null && echo OK
```

## Milestone status

| Milestone | Status |
|-----------|--------|
| 0 Upstream review | done |
| 1 Repository + compose | done |
| 2 Paperclip | done (`http://localhost:3100`) |
| 3 Hermes | done (`127.0.0.1:8642`) |
| 4 Decider | done (`scripts/smoke-decider.sh`) |
| 5 Decision gateway | done (`scripts/smoke-decision.sh`) |
| 6 E2E decision flow | done (`scripts/smoke-e2e-decision.sh`) |
| 7 Model provider | done (`scripts/smoke-model.sh`, default stub) |
| 8–10 Personal assistant + weather + daily brief | done (`scripts/generate-daily-brief.sh`; Paperclip Routine 07:00 Europe/Madrid) |

## Paperclip daily brief routine

Scheduled at **07:00 Europe/Madrid** (`0 7 * * *`) via Paperclip Routines → Hermes Runtime.

```bash
./scripts/ensure-hermes-paperclip-key.sh  # once: agent API key → data/hermes/.env
./scripts/ensure-daily-brief-routine.sh   # idempotent create/update
./scripts/run-daily-brief-routine.sh      # manual fire + wait for Hermes
```

Hermes `data/hermes/config.yaml` should have `approvals.mode: off` so unattended `curl` is not blocked. Pause/edit in the Paperclip UI (Routines). Host-only smoke without Paperclip: `./scripts/generate-daily-brief.sh`.

## Local assumptions

- `PAPERCLIP_DEPLOYMENT_MODE=authenticated` + `PAPERCLIP_BIND=lan` for Docker
  (upstream forbids `local_trusted` with non-loopback binds).
- Decider defaults to `Mapika/decider-2b` on CPU. The image uninstalls
  `flash-linear-attention` / Triton so Transformers uses its pure-PyTorch
  Qwen3.5 kernels (`USE_HUB_KERNELS=NO`).
- Hermes dashboard is disabled by default.
