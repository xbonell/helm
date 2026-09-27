# AGENTS.md

## Repo Shape
- Docker Compose stack. Base topology in `compose.yaml`; local port publishes in `compose.override.yaml`.
- Core services: `paperclip`, `hermes`, `decider`, `decision-gateway`, `model-router`, `personal-assistant`.
- Persistent state lives under `data/`; do not delete it unless user wants reset.

## Start / Verify
- First-time setup: `./scripts/bootstrap.sh`.
- Start / stop: `docker compose up -d` / `docker compose down`.
- Health check: `./scripts/healthcheck.sh`.
- Daily brief smoke: `./scripts/generate-daily-brief.sh`.
- Compose validation without startup: `set -a && source .env && set +a && docker compose config >/dev/null`.

## Required Env
- `BETTER_AUTH_SECRET` and `HERMES_API_SERVER_KEY` are required for compose.
- `./scripts/bootstrap.sh` creates `.env` and seeds `data/hermes/.env` from `.env.example`.

## Service Rules
- Paperclip must use `PAPERCLIP_DEPLOYMENT_MODE=authenticated` and `PAPERCLIP_BIND=lan` in Docker.
- Hermes API auth must match `HERMES_API_SERVER_KEY` in `.env` and `data/hermes/.env`.
- Decider is internal-only on `8000`; reach it through `decision-gateway`.
- `model-router` defaults to `MODEL_PROVIDER=stub`.

## Files To Respect
- `README.md`, `docs/architecture.md`, and `docs/development.md` are the source of repo workflow.
- `compose.yaml` is source of truth for service wiring; `compose.override.yaml` only adds local ports.
- `scripts/bootstrap.sh` is source of truth for initial state seeding.

## Testing Notes
- Python service tests live beside service code and are typically run from service dir with `pytest`.
- Prefer focused checks over full-stack runs when touching one service.
