# Deployment (Hetzner VPS)

Same Compose stack as local. Production adds reverse proxy, TLS, firewall, backups, and monitoring later — not required for the local MVP.

## Target

- Single x86_64 Hetzner VPS
- Docker Engine + Compose v2
- No Kubernetes

## Approximate flow

```bash
git clone <repository>
cp .env.production.example .env   # when provided
# or: cp .env.example .env && edit
./scripts/bootstrap.sh            # if data dirs / secrets need seeding
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
```

Use **base** `compose.yaml` only (skip `compose.override.yaml` host-wide binds), then put Paperclip behind a reverse proxy bound to `127.0.0.1:3100`.

## Production hardening checklist

- [ ] `PAPERCLIP_DEPLOYMENT_MODE=authenticated`
- [ ] Strong unique `BETTER_AUTH_SECRET` and `HERMES_API_SERVER_KEY`
- [ ] Reverse proxy + TLS (Caddy / Traefik / nginx)
- [ ] Firewall: only 80/443 (and SSH) public
- [ ] Do **not** publish Decider (`8000`) or Postgres
- [ ] Hermes API on loopback or private network only
- [ ] Scheduled `scripts/backup.sh` (and off-box copy)
- [ ] Pin image digests for Paperclip and Hermes

## Persistence & restore

Backup:

```bash
./scripts/backup.sh
# optional: INCLUDE_HF=1 ./scripts/backup.sh
```

Restore onto a new host:

```bash
docker compose down
tar -xzf data/backups/helm-backup-XXXX.tar.gz
docker compose up -d
```

Decider weights re-download from Hugging Face if `data/decider-hf` was excluded from the archive.

## Resources

| Component | Guidance |
|-----------|----------|
| VPS RAM | 16 GB minimum if running Decider-2B on CPU; 8 GB if Decider is deferred |
| Disk | 40+ GB (model cache + Paperclip/Hermes state) |
| CPU | 4+ cores recommended for Decider CPU inference |
