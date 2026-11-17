#!/usr/bin/env bash
# Set up one GitHub repo for the Helm hosted dev lane.
# Spec: docs/superpowers/specs/2026-11-14-hosted-dev-lane-design.md
#
# Usage: scripts/setup-dev-repo.sh <owner/name> [--checks "CI / test,lint"]
#
# Does (idempotent):
#   - installs .github/workflows/helm-dev.yml and .github/helm-dev-notify.sh
#     from templates/ (commits to the default branch only when they differ)
#   - creates or updates the helm-dev label
#   - attempts branch protection on the default branch (PR required, optional
#     required checks); warns and continues where the plan refuses it
#   - lists workflows that run on push and prints the deploy guard for each
#     (never edits them)
#   - prints the manual steps that remain (Claude GitHub App, missing secrets)
#
# Never changes repository visibility. Never reads or prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="helm-dev"
# Agent runs act as claude[bot] (PRs, comments) but its git pushes are
# recorded as github-actions[bot] (observed in M1), so guard both.
APP_ACTORS=("claude[bot]" "github-actions[bot]")
SECRETS=(CLAUDE_CODE_OAUTH_TOKEN HELM_TELEGRAM_BOT_TOKEN HELM_TELEGRAM_CHAT_ID)

usage() {
  echo "Usage: $0 <owner/name> [--checks \"check one,check two\"]" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
repo="$1"; shift
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || usage
checks=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --checks) [[ $# -ge 2 ]] || usage; checks="$2"; shift 2 ;;
    *) usage ;;
  esac
done

for cmd in gh jq base64; do
  command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }
done
gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated. Run: gh auth login" >&2; exit 1; }

failed=0
manual=()

info=$(gh repo view "$repo" --json defaultBranchRef,visibility) \
  || { echo "Cannot read $repo with gh." >&2; exit 1; }
branch=$(jq -r .defaultBranchRef.name <<<"$info")
visibility=$(jq -r .visibility <<<"$info")
echo "Repo: $repo (default branch: $branch, visibility: $visibility; visibility is never changed)"
echo

# --- 1. files --------------------------------------------------------------
install_file() {
  local src="$1" dest="$2" local_b64 remote sha remote_b64 body out
  local_b64=$(base64 -w0 < "$src")
  sha=""
  if remote=$(gh api "repos/$repo/contents/$dest?ref=$branch" 2>/dev/null); then
    sha=$(jq -r .sha <<<"$remote")
    remote_b64=$(jq -r .content <<<"$remote" | base64 -d | base64 -w0)
    if [[ "$remote_b64" == "$local_b64" ]]; then
      echo "  $dest: unchanged"
      return 0
    fi
  fi
  body=$(jq -n --arg m "chore: install $dest from helm templates" --arg c "$local_b64" \
    --arg b "$branch" --arg s "$sha" \
    '{message:$m, content:$c, branch:$b} + (if $s == "" then {} else {sha:$s} end)')
  if out=$(gh api -X PUT "repos/$repo/contents/$dest" --input - <<<"$body" 2>&1); then
    if [[ -n "$sha" ]]; then echo "  $dest: updated"; else echo "  $dest: created"; fi
  else
    echo "  $dest: FAILED: $(head -c 300 <<<"$out")"
    if [[ "$dest" == .github/workflows/* ]]; then
      echo "    Writing workflow files needs the 'workflow' scope. Run:"
      echo "      gh auth refresh -h github.com -s workflow"
    fi
    failed=1
  fi
}

echo "Files:"
install_file "$ROOT/templates/helm-dev.yml" ".github/workflows/helm-dev.yml"
install_file "$ROOT/templates/helm-dev-notify.sh" ".github/helm-dev-notify.sh"
echo

# --- 2. label --------------------------------------------------------------
echo "Label:"
if gh label create "$LABEL" -R "$repo" --color 5319e7 \
     --description "Run the Helm dev lane (Claude Code Action) on this issue" --force >/dev/null; then
  echo "  $LABEL: present"
else
  echo "  $LABEL: FAILED"; failed=1
fi
echo

# --- 3. branch protection --------------------------------------------------
echo "Branch protection on $branch:"
if [[ -n "$checks" ]]; then
  status_checks=$(jq -n --arg c "$checks" '{strict:false, contexts:($c | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(. != "")))}')
else
  status_checks=null
fi
protection=$(jq -n --argjson sc "$status_checks" '{
  required_status_checks: $sc,
  enforce_admins: false,
  required_pull_request_reviews: {required_approving_review_count: 0},
  restrictions: null
}')
if out=$(gh api -X PUT "repos/$repo/branches/$branch/protection" --input - <<<"$protection" 2>&1); then
  echo "  enabled: pull request required${checks:+, required checks: $checks}"
  [[ -n "$checks" ]] || echo "  note: no required checks set; pass --checks to require CI"
elif grep -q "Upgrade to GitHub Pro" <<<"$out"; then
  cat <<EOF
  ################################################################
  WARNING: $repo has NO enforced review gate.
  GitHub refused branch protection: "Upgrade to GitHub Pro or make
  this repository public to enable this feature."
  The agent's job can push to $branch. Only the prompt asks for a PR.
  Detection: the helm-dev Telegram message warns if $branch moves.
  Containment: add the deploy guard below to deploy/publish workflows.
  See "Open decision: review gate on private repos" in the spec.
  ################################################################
EOF
else
  echo "  FAILED: $(head -c 300 <<<"$out")"; failed=1
fi
echo

# --- 4. workflows that run on push (listed, never edited) -----------------
echo "Workflows that run on push (check each that deploys or publishes):"
found=0
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  [[ "$(basename "$path")" == helm-dev.yml ]] && continue
  content=$(gh api "repos/$repo/contents/$path?ref=$branch" --jq .content 2>/dev/null | base64 -d 2>/dev/null || true)
  if grep -qE '^[[:space:]]*push:|^[[:space:]]*"?on"?:[[:space:]]*(push|\[.*push.*\])|^[[:space:]]*-[[:space:]]*push[[:space:]]*$' <<<"$content"; then
    found=1
    echo "  $path"
  fi
done < <(gh api "repos/$repo/contents/.github/workflows?ref=$branch" --jq '.[] | select(.type=="file") | select(.name|test("\\.ya?ml$")) | .path' 2>/dev/null || true)
if [[ $found -eq 1 ]]; then
  cat <<EOF
  If a workflow above deploys or publishes on push to $branch, add this to
  each such job so pushes made by helm-dev agent runs do not deploy:
      if: github.actor != '${APP_ACTORS[0]}' && github.actor != '${APP_ACTORS[1]}'
EOF
else
  echo "  none"
fi
echo

# --- 5. remaining manual steps --------------------------------------------
manual+=("Install the Claude GitHub App on $repo if not already: https://github.com/apps/claude")
present=$(gh secret list -R "$repo" --json name --jq '.[].name' 2>/dev/null || true)
for s in "${SECRETS[@]}"; do
  grep -qx "$s" <<<"$present" || manual+=("Add repo secret $s:  gh secret set $s -R $repo")
done

echo "Remaining manual steps:"
for m in "${manual[@]}"; do echo "  - $m"; done

if [[ $failed -ne 0 ]]; then
  echo
  echo "Some steps failed (see above). Fix and re-run; the script is idempotent." >&2
  exit 1
fi
