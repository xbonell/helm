# Hosted Dev Lane — Milestone 1 Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Approved by the operator on 2026-11-16.
> On approval this file is committed as `docs/superpowers/plans/2026-11-14-hosted-dev-lane-m1.md` on branch `feat/hosted-dev-lane-m1` (same format as `2026-09-28-google-calendar-agenda.md`). Approval of this plan = the "stop for my review" gate in the handoff.

**Goal:** Prove the hosted dev lane end to end on `xbonell/helm-dev-lane-test`: label an issue `helm-dev` → Claude Code Action → PR → CI on the PR → Telegram message; settle spec checks 1–8.

**Architecture:** Three files in Helm, no service code. `templates/helm-dev.yml` + `templates/helm-dev-notify.sh` are copied into a target repo by `scripts/setup-dev-repo.sh` using `gh`. The workflow runs on a GitHub-hosted runner, authenticates as the Claude GitHub App (no `github_token`), and on the operator's subscription (`claude_code_oauth_token`).

**Tech stack:** GitHub Actions, `anthropics/claude-code-action@v1` (v1.0.277 as of 2026-11-16), bash, `gh`, `jq`, `curl`, Telegram Bot API.

**Spec:** `docs/superpowers/specs/2026-11-14-hosted-dev-lane-design.md` (contains "Open decision: review gate on private repos" — checked).

## Context

Spec workflow was composed from docs and never run. M1 is the cheap, throwaway proof before any Helm service work (M2/M3). If the action can't produce a PR or CI doesn't run on it, the design is revisited — operator's decision.

## Global constraints

- Touch only `templates/`, `scripts/setup-dev-repo.sh`, the plan doc. No `services/`, `compose*.yaml`, `.env.example`, `scripts/bootstrap.sh`, `data/`.
- Only `xbonell/helm-dev-lane-test` for GitHub actions. Never change repo visibility.
- No Anthropic API key; no `github_token` input. Run bounds: `timeout-minutes: 30`, `--max-turns 50`, `concurrency: helm-dev`.
- Never print/log/commit tokens. Notify exits 0 quietly when Telegram secrets unset.
- Agent push to main = finding to report, not tidy up.
- Branch + small commits; open PR, don't merge.

## Doc findings vs spec (read 2026-11-16; scratch copies of action docs fetched via `gh api`)

Not blocking, but flagged per handoff:

1. **Fallback PR step can't use the App token.** Spec: "the fallback is a deterministic step that opens the PR from the branch using an App token." `action.yml` has `- name: Revoke app token` with `if: always() && inputs.github_token == '' ...` at the end of the action step, so a later step has no App token. A PR opened with `GITHUB_TOKEN` won't trigger CI (faq.md: "The `github-actions` user cannot trigger subsequent GitHub Actions workflows"). A working fallback would need an operator PAT secret — a spec change, so I stop and ask if the primary path fails.
2. **PR creation needs a tool decision.** faq.md: "Claude doesn't create PRs by default. Instead, it pushes commits to a branch and provides a link to a pre-filled PR submission page." configuration.md: "In auto mode, the default, a safety review decides any Bash command that no allow rule covers." So `gh pr create` from the prompt depends on the safety review. Plan: run 1 exactly as spec (prompt only) to answer check 1 honestly; if no PR, add `--allowedTools "Bash(gh pr create:*),Bash(gh issue comment:*)"` to `claude_args` and re-run. Recorded as deviation if needed.
3. **`label_trigger` defaults to `"claude"`** (`action.yml`). Template sets `label_trigger: helm-dev` explicitly so the action's own label check matches the job `if:`.
4. **Branch name.** security.md: "With `prompt`, a run on an issue commits to `issue-N`" and "Claude's push command can't update any other branch." Supports check 7; notify uses the action's `branch_name` output to find the PR.
5. **App has no workflow write** (faq.md) — agent can't edit `.github/workflows/`. Setup script writes them with operator's `gh`, whose token currently lacks `workflow` scope (`gh auth status`: `gist, read:org, repo`) → operator must run `gh auth refresh -h github.com -s workflow` before Task 4. Script detects and prints this.
6. **Usage limits:** no doc mentions how a subscription limit surfaces. Check 5 is observational.

## File map

| File | Responsibility |
|------|----------------|
| `templates/helm-dev.yml` | Workflow: label gate, record base SHA, stash notify script, run action, notify `if: always()` |
| `templates/helm-dev-notify.sh` | Build one plain-text message (PR link / run link / default-branch warning), send via Telegram, dry-run mode |
| `scripts/setup-dev-repo.sh` | Idempotent installer for one `owner/name`; protection attempt; push-workflow listing + deploy guard; remaining manual steps |
| `docs/superpowers/plans/2026-11-14-hosted-dev-lane-m1.md` | This plan |

---

### Task 1: Workflow template

**Files:** Create `templates/helm-dev.yml`

Start from spec sketch, with these changes (each listed in PR as deviation):
- `label_trigger: helm-dev` on the action.
- `id: claude` on the action step; pass `BRANCH: ${{ steps.claude.outputs.branch_name }}`, `CONCLUSION: ${{ steps.claude.outputs.conclusion }}`, `EXECUTION_FILE: ${{ steps.claude.outputs.execution_file }}` to notify.
- New step before the action: copy `.github/helm-dev-notify.sh` to `$RUNNER_TEMP` — the agent works in the checkout and could alter the script before the `always()` step runs. Notify runs `bash "$RUNNER_TEMP/helm-dev-notify.sh"` (also avoids exec-bit issues; contents API can't set mode).
- Keep: `issues: [labeled]`, `if: github.event.label.name == 'helm-dev'`, concurrency, 30 min, permissions set, `actions/checkout@v6`, "Record default branch" step, `claude_args: "--max-turns 50"`, prompt text, auto mode.

- [ ] Write file; validate YAML parses: `python3 -c` with a tiny loader isn't available (no PyYAML) → `npx --yes yaml@2 valid < templates/helm-dev.yml` or `actionlint` via `docker run rhysd/actionlint` if allowed.
- [ ] Commit.

### Task 2: Notify script

**Files:** Create `templates/helm-dev-notify.sh`

Interface: `helm-dev-notify.sh <job_status> <issue_number>`; env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GH_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_SERVER_URL`, `GITHUB_RUN_ID`, `DEFAULT_BRANCH`, `BASE_SHA`, `BRANCH`, `EXECUTION_FILE`, optional `HELM_DEV_NOTIFY_DRY_RUN=1` (print message to stdout, don't send).

Logic:
1. `set -uo pipefail`, never `set -x`. Telegram vars unset and not dry-run → exit 0 silently.
2. Default-branch check: `gh api repos/$R/commits/$DEFAULT_BRANCH --jq .sha`; if ≠ `BASE_SHA` → `gh api repos/$R/compare/$BASE_SHA...$HEAD` → lines `short-sha author.login (committer.login): subject`. Message leads with `⚠ main moved during run` + list. Missing `BASE_SHA` → say "default-branch check unavailable".
3. PR lookup: `gh pr list -R $R --head "$BRANCH" --state all --json url,number` ; fallback `gh pr list --search "#$ISSUE in:body"`; fallback `gh api` branch existence → "branch pushed, no PR: <compare URL>".
4. Status line: success+PR → `✅ PR: <url>`; otherwise `❌ helm-dev run <status> for #N: <run url>`. If `EXECUTION_FILE` readable and matches `/usage limit|rate limit|limit reached/i` → add "Claude usage limit hit; re-apply label later" (pattern updated after check 5).
5. Send: `curl -sS -o /dev/null -w '%{http_code}' --data-urlencode "chat_id=..." --data-urlencode "text=..."` to `https://api.telegram.org/bot$TOKEN/sendMessage` (token only in URL, curl not verbose; `--fail-with-body` off to avoid echoing). Non-200 → print code only, exit 0 (never fail job on notify).

- [ ] Local tests (scratchpad, no tokens): unset vars → no output exit 0; dry-run with stubbed `gh` on PATH covering: success+PR, failure no PR, main moved, usage-limit text.
- [ ] `bash -n`; shellcheck via `docker run koalaman/shellcheck` if available, else skip & note.
- [ ] Commit.

### Task 3: Setup script

**Files:** Create `scripts/setup-dev-repo.sh` (exec bit)

Behaviour:
1. Require exactly one arg matching `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`, else usage + exit 2. Check `gh`, `jq`, auth.
2. Read default branch (`gh repo view --json defaultBranchRef,visibility`). Print visibility; never change it.
3. Install `templates/helm-dev.yml` → `.github/workflows/helm-dev.yml` and `templates/helm-dev-notify.sh` → `.github/helm-dev-notify.sh` via `gh api -X PUT repos/R/contents/PATH` (base64 content, `sha` when exists). Idempotent: compare remote blob content first; identical → "unchanged". 404/403 on workflow path with missing `workflow` scope → print `gh auth refresh -h github.com -s workflow` hint, continue to other steps, exit non-zero at end.
4. Label: `gh label create helm-dev -R R --color ... --description ... --force`.
5. Protection: `gh api -X PUT repos/R/branches/$DEFAULT/protection` with `required_pull_request_reviews.required_approving_review_count: 0` (single operator can't approve own PR), `enforce_admins: false`, `required_status_checks` from optional `--checks a,b` (none → `null` + note), `restrictions: null`. On response containing "Upgrade to GitHub Pro" → loud `WARNING: no enforced review gate on R` block, continue. Already protected → re-PUT is idempotent.
6. Push workflows: list `.github/workflows/*` via contents API, fetch each (skip `helm-dev.yml`), heuristic match of a `push` trigger (`^\s*push:`, `on: push`, `on: [ ... push ...]`), print file + guard `if: github.actor != 'claude[bot]'` (value from check 8; `claude[bot]` is the action's `bot_name` default, to be confirmed). Never edits.
7. Remaining manual steps: Claude App install link `https://github.com/apps/claude`; `gh secret list` → print only missing names of the three secrets (names only, never values).

- [ ] `bash -n`; run with no arg / bad arg → refuses.
- [ ] Commit.

### Task 4: Install on test repo

Needs operator: `gh auth refresh -h github.com -s workflow` (I'll ask).
- [ ] `./scripts/setup-dev-repo.sh xbonell/helm-dev-lane-test` → expect files committed to main, label created, protection 403 warning, `ci.yml` listed with guard.
- [ ] Run again → all "unchanged" (idempotency).

### Task 5: Live runs (checks 1–8)

| Run | How | Settles |
|-----|-----|---------|
| A | I create issue with `gh issue create --label helm-dev` (README idea: accent stripping) | 3 (does labeled fire at creation), 1, 2, 7, 8, 6, Done-when |
| A' | If A's PR not opened: add `--allowedTools` rule (finding 2), re-label | 1 |
| B | Issue created without label, I add label by hand | trigger baseline if A didn't fire |
| C | Issue opened with operator's fine-grained PAT (I ask operator to create it; used via `GH_TOKEN` env in one command, never written to disk) | 4 |
| D | Impossible instruction issue | failure Telegram w/ run link |
| E | During a run I ask operator to push to main | default-branch warning lists commits |

Observation commands: `gh run list/view --json`, `gh api repos/R/actions/runs/ID/timing` (minutes), `gh pr view --json author,url,body`, `gh run list --event pull_request` (CI on PR), `gh api repos/R/commits?sha=main` (agent commits on main?), `gh api repos/R/events` PushEvent `actor.login` (check 8). Check 5: record any limit hit; otherwise "not observed" + log format of failures. Check 6: compare per-run timing to plan allowance (operator's plan; Free = 2,000 min/month on private repos — confirm with operator).

Stop and report (no workaround) if: no PR possible, CI doesn't run on PR, agent pushes to main, App auth fails (ask operator to check App install).

### Task 6: Fold findings back + PR

- [ ] Update templates with confirmed actor name / usage-limit pattern / allowlist if needed; re-run `setup-dev-repo.sh` (shows idempotent update).
- [ ] Open PR on `xbonell/helm` with: checks 1–8 observations, deviations, notes for M2 (e.g. label-at-creation result, PAT result, fallback-needs-PAT finding). Don't merge.

## Verification (Done when)

- Labelled issue → open PR referencing issue, CI run on PR, Telegram with PR link, no agent commit on main.
- Failing run → Telegram with run link.
- Operator push mid-run → warning with commits listed.
- `setup-dev-repo.sh` second run makes no changes; refuses without arg.

## Spec coverage

| Spec item | Task |
|-----------|------|
| Workflow + Record default branch | 1 |
| Notify, default-branch check, quiet when unset | 2 |
| Setup steps 3–5, protection refusal warning, push-workflow guard listing | 3, 4 |
| Remaining checks 1–8 | 5 |
| Report deviations | 6 |
