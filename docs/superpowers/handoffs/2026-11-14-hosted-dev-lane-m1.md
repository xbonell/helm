# Handoff prompt: hosted dev lane, milestone 1

Paste everything inside the block below into the agent that will do the work.
Spec: [2026-11-14-hosted-dev-lane-design.md](../specs/2026-11-14-hosted-dev-lane-design.md).

```text
You are picking up work in the repo xbonell/helm (a self-hosted Docker Compose
stack for personal AI agents). Start by pulling main and reading, in this order:

1. AGENTS.md
2. docs/superpowers/specs/2026-11-14-hosted-dev-lane-design.md   (the adopted design; source of truth)
3. docs/superpowers/plans/2026-09-28-google-calendar-agenda.md   (example of this repo's plan format)

Before anything else, confirm the spec contains a section titled
"Open decision: review gate on private repos". If it does not, stop and tell me:
the spec on main is out of date.

Do NOT implement docs/superpowers/specs/2026-11-13-unimatrix-dev-lane-design.md.
It is superseded and kept only for its reasoning. The xbonell/unimatrix repo is
archived and plays no part in this work.

## Goal of this session

Deliver Milestone 1 of the hosted dev-lane spec, and nothing beyond it:

- templates/helm-dev.yml          GitHub Actions workflow for target repos, including
                                  the "Record default branch" step from the spec
- templates/helm-dev-notify.sh    Telegram result message, run as the workflow's last
                                  step, including the default-branch check
- scripts/setup-dev-repo.sh <owner/name>   installs the workflow, notify script and
                                           `helm-dev` label with `gh`, attempts branch
                                           protection, then prints the manual steps
                                           that remain

Milestone 1 touches no Helm service code: no changes to services/, compose.yaml,
compose.override.yaml, .env.example or scripts/bootstrap.sh. Milestones 2 and 3
(personal-assistant endpoints, Hermes planner skill, daily brief section) are out
of scope for this session.

## Test repo

Use xbonell/helm-dev-lane-test for every GitHub action in this milestone. It is
private, plain Node.js 24 with no dependencies, and has one workflow, "CI", that
runs `npm test` on pull requests and on push to main. Its README lists small issue
ideas you can use as test requests. Do not use any other repo of mine.

Known issue: branch protection and repository rulesets are NOT available on private
repos under my current GitHub plan. Both APIs return "Upgrade to GitHub Pro or make
this repository public to enable this feature." Therefore:

- scripts/setup-dev-repo.sh must detect the refusal, print a clear warning that the
  repo has no enforced review gate, and still complete.
- Never make a repo public, and never change any repo's visibility, to work around it.
- The agent's job can technically push to main. Treat any direct push to main by
  the agent as a finding to report, not something to tidy up quietly.

## How to work

1. Write an implementation plan at
   docs/superpowers/plans/2026-11-14-hosted-dev-lane-m1.md, following the format of
   the existing plans, and stop for my review before implementing.
2. Work on a branch, not on main. Commit in small steps. Open a PR when done; do
   not merge it.

## Things you must verify, not assume

The workflow in the spec was composed from documentation and has never been run.
Before relying on any input name or behaviour, check the current docs:

- https://code.claude.com/docs/en/github-actions
- https://github.com/anthropics/claude-code-action  (README and docs/ folder)

Milestone 1 exists to settle checks 1 to 8 in the spec's "Remaining checks"
section. (Check 9 belongs to milestone 2.) For each one, record what you observed
in the PR description:

1. PR creation: does the prompt reliably make the action open a PR, or is the
   deterministic fallback step needed? (By default the action only returns a
   PR-creation link.)
2. CI on the PR: does a PR created under the Claude GitHub App identity trigger
   the repo's CI?
3. Label at creation: does an issue created with the label already applied fire
   the `labeled` event?
4. PAT-authored events: does an issue opened with my fine-grained PAT pass the
   action's actor checks?
5. Usage limit: how does the action report a subscription usage limit?
6. Actions minutes: how many minutes does a typical run use?
7. Direct pushes: from the branch history, did every agent run produce a branch
   and a PR, and never a commit on main?
8. App actor name: what exact `github.actor` value do pushes by the Claude GitHub
   App carry? Put that value into the deploy guard the setup script prints.

## What is already set up on the test repo

- The Claude GitHub App is enabled for all my repositories. I have not confirmed
  it covers this repo specifically; if the action fails to authenticate, check
  this first and tell me.
- These repo secrets exist (set 2026-11-16): CLAUDE_CODE_OAUTH_TOKEN,
  HELM_TELEGRAM_BOT_TOKEN, HELM_TELEGRAM_CHAT_ID. Their values are untested.
- The Claude token expires around 2027-11-16.

## Steps only I can do

Tell me when you need these, and wait. Do not try to do them yourself.

- Creating the fine-grained PAT needed to test check 4.
- Replacing any of the three secrets, if one turns out to be wrong.
- Anything involving the Claude GitHub App's installation.

Never print, log, commit or paste any token. The notify script must exit quietly
when the Telegram secrets are unset, and must not echo them.

## Constraints

- Authentication is my Claude subscription via `claude_code_oauth_token`. Do not
  introduce an Anthropic API key anywhere.
- Do not pass `github_token` to the action; it must authenticate as the Claude
  GitHub App so CI runs on its commits.
- Keep the run bounds from the spec: job timeout 30 minutes, --max-turns 50, one
  run at a time via `concurrency`.
- Do not delete or modify anything under data/.
- scripts/setup-dev-repo.sh must be idempotent, must refuse to run without an
  explicit owner/name argument, and must only list (never edit) the target repo's
  workflows that run on push to the default branch, printing the deploy guard for
  each.

## Done when

Hand-labelling an issue `helm-dev` in the test repo ends in:
- an open pull request that references the issue,
- the repo's CI running on that pull request,
- a Telegram message containing the pull request link, and
- no commit by the agent on main.

Two failure paths must also work:
- A deliberately failing run (for example an impossible instruction) produces a
  Telegram message with the workflow run link.
- A push to main made by me during a run produces the default-branch warning,
  with the new commits listed. Ask me to make that push; do not make it yourself.

## Stop and report instead of working around it if

- the action cannot be made to produce a PR, or CI does not run on it. The spec
  says the design choice is revisited in that case, and that decision is mine.
- the agent pushes directly to main.
- anything in the current docs contradicts the spec. Quote the passage and ask.

## What to report at the end

- The PR link.
- The observed answer to each of the eight checks above.
- Any deviation from the spec and why.
- What Milestone 2 should know that the spec does not already say.
```
