#!/usr/bin/env bash
# Installed into target repos as .github/helm-dev-notify.sh by
# scripts/setup-dev-repo.sh in xbonell/helm. Edit the template there, not here.
#
# Sends one Telegram message with the result of a helm-dev run:
#   - PR link on success, workflow run link otherwise
#   - a leading warning, with the new commits, if the default branch moved
#     during the run (whatever the job status)
#
# Usage: helm-dev-notify.sh <job_status> <issue_number>
# Env:   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (unset -> exit quietly)
#        GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SERVER_URL, GITHUB_RUN_ID
#        DEFAULT_BRANCH, BASE_SHA, BRANCH, EXECUTION_FILE  (optional)
#        HELM_DEV_NOTIFY_DRY_RUN=1  print the message instead of sending it
#
# Never prints tokens. Never fails the job.
set -uo pipefail

status="${1:-unknown}"
issue="${2:-?}"
dry_run="${HELM_DEV_NOTIFY_DRY_RUN:-}"

if [[ -z "$dry_run" && ( -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ) ]]; then
  exit 0
fi

repo="${GITHUB_REPOSITORY:-}"
server="${GITHUB_SERVER_URL:-https://github.com}"
run_url="$server/$repo/actions/runs/${GITHUB_RUN_ID:-}"
default_branch="${DEFAULT_BRANCH:-main}"
base_sha="${BASE_SHA:-}"
branch="${BRANCH:-}"

# --- default-branch check -------------------------------------------------
warning=""
head_sha="$(gh api "repos/$repo/commits/$default_branch" --jq .sha 2>/dev/null || true)"
if [[ -z "$base_sha" || -z "$head_sha" ]]; then
  warning="⚠ Default-branch check unavailable for $default_branch. Check its history by hand."
elif [[ "$head_sha" != "$base_sha" ]]; then
  commits="$(gh api "repos/$repo/compare/$base_sha...$head_sha" \
    --jq '.commits[] | "- \(.sha[0:7]) \(.commit.author.name) [login: \(.author.login // "none")]: \(.commit.message | split("\n")[0])"' \
    2>/dev/null || true)"
  warning="⚠ $default_branch moved during this run. New commits:
${commits:-  (could not list commits; compare $server/$repo/compare/$base_sha...$head_sha)}"
fi

# --- PR lookup ------------------------------------------------------------
pr_url=""
if [[ -n "$branch" ]]; then
  pr_url="$(gh pr list -R "$repo" --head "$branch" --state all --json url --jq '.[0].url // empty' 2>/dev/null || true)"
fi
if [[ -z "$pr_url" && "$issue" =~ ^[0-9]+$ ]]; then
  pr_url="$(gh pr list -R "$repo" --state all --search "#$issue in:body" --json url --jq '.[0].url // empty' 2>/dev/null || true)"
fi

# --- status line ----------------------------------------------------------
if [[ "$status" == "success" && -n "$pr_url" ]]; then
  result="✅ helm-dev $repo #$issue: PR $pr_url"
elif [[ "$status" == "success" ]]; then
  result="⚠ helm-dev $repo #$issue: run succeeded but no PR found."
  if [[ -n "$branch" ]]; then
    result+="
Branch: $server/$repo/compare/$default_branch...$branch"
  fi
  result+="
Run: $run_url"
else
  result="❌ helm-dev $repo #$issue: run $status.
Run: $run_url"
  if [[ -n "$pr_url" ]]; then
    result+="
PR: $pr_url"
  fi
fi

if [[ -n "${EXECUTION_FILE:-}" && -r "${EXECUTION_FILE:-}" ]] \
  && grep -qiE 'usage limit|rate limit|limit reached|limit will reset' "$EXECUTION_FILE"; then
  result+="
Claude usage limit hit. Re-apply the helm-dev label later."
fi
if [[ -n "${EXECUTION_FILE:-}" && -r "${EXECUTION_FILE:-}" ]] \
  && grep -qiE 'authentication_failed|OAuth access token is invalid' "$EXECUTION_FILE"; then
  result+="
Claude token rejected (401). Replace the CLAUDE_CODE_OAUTH_TOKEN secret."
fi

if [[ -n "$warning" ]]; then
  message="$warning

$result"
else
  message="$result"
fi

# --- send -----------------------------------------------------------------
if [[ -n "$dry_run" ]]; then
  printf '%s\n' "$message"
  exit 0
fi

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
  --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
  --data-urlencode "text=$message" \
  --data-urlencode "disable_web_page_preview=true" \
  "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" 2>/dev/null || true)"
if [[ "$code" != "200" ]]; then
  echo "helm-dev-notify: Telegram send failed (HTTP ${code:-none})"
fi
exit 0
