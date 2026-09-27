#!/usr/bin/env bash
# Backup persistent Helm state to data/backups/.
# Restore: see docs/deployment.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="data/backups/helm-backup-${stamp}.tar.gz"
mkdir -p data/backups

# Exclude Hugging Face model cache by default (large, re-downloadable).
# Pass INCLUDE_HF=1 to include it.
paths=(data/paperclip data/hermes)
if [[ "${INCLUDE_HF:-0}" == "1" ]]; then
  paths+=(data/decider-hf)
fi

tar -czf "$out" "${paths[@]}"
echo "Wrote ${out}"
ls -lh "$out"
