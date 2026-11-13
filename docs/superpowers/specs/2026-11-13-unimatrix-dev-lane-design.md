# Helm × Unimatrix: software-development lane (design)

**Date:** 2026-11-13
**Status:** draft; open questions resolved in chat on 2026-11-13; awaiting spec file review before any implementation plan
**Repos touched:** `xbonell/helm` (this spec's home) and `xbonell/unimatrix`

## Goal

Make Helm a single personal "swarm" that covers both personal-assistant work and software-development work on the operator's own projects, by using Unimatrix as the development lane instead of building a second dev workflow inside Helm.

The target experience:

1. Operator sends Hermes a Telegram message such as "in `xbonell/foo`, add retry to the weather client".
2. Helm publishes that as a Unimatrix `WorkUnit` (a GitHub issue) in the target repo.
3. A worker inside the Helm stack claims it, runs a coding agent, and opens a PR.
4. GitHub Actions runs the mechanical checks; the operator reviews and approves the PR.
5. `dev-worker` sends the PR link on Telegram, and the daily brief lists outstanding dev work.

## Context

- Helm today: Paperclip (control plane) → Hermes (runtime) → small FastAPI services. One real capability, the daily brief. The Decider route already offers a `development` candidate that nothing handles. Priorities in the brief are mocked.
- Unimatrix today (M4): protocol `0.1.0`, GitHub Lite provider, local Cursor adapter, CLI with `publish`, `claim`, `run`, `submit`, `claim-run-submit`, `record-outcome`, `doctor`. Every step is typed by a human; there is no daemon, no planner, and the only adapter needs a local Cursor setup.
- The two are complementary: Helm has the always-on runtime, scheduler, chat channel and memory; Unimatrix has the work definition, lease state machine, and validation gates.

## Decisions

| Topic | Choice | Why |
|-------|--------|-----|
| Repository shape | **Two repos, one product.** Helm consumes Unimatrix; no code merge | Python Compose stack vs TypeScript library; Unimatrix's protocol must stay free of runtime dependencies |
| Source of truth for dev work | **GitHub** (Unimatrix Lite: issues, PRs, checks) | Already built and auditable; avoids coupling to Paperclip's data model |
| Paperclip's role | Trigger only (routines); no Paperclip issues or comments for dev work | Same pattern as the daily brief, minus issue comments, which would wake the Hermes agent |
| Where the worker runs | New Compose service **`dev-worker`** (Node 24) | Needs `@unimatrix/*` packages; matches Helm's one-service-per-capability layout |
| How Helm gets Unimatrix | Docker build from a **pinned git SHA** of `xbonell/unimatrix` | Not published to npm; pin keeps protocol `0.x` breaking changes deliberate |
| Headless adapter | New **`@unimatrix/adapter-claude-code`** that shells out to the unmodified Claude Code CLI (`claude -p`) | Runs on the operator's Claude subscription with no metered API key; Cursor local SDK does not suit a server |
| Model credential for coding | **`CLAUDE_CODE_OAUTH_TOKEN`** from `claude setup-token` (one-year token) | Documented path for scripts and CI on a subscription; the Agent SDK is documented as API-key only |
| Coding auth fallback | Explicit switch **`DEV_WORKER_AUTH=subscription\|api_key`**, default `subscription` | Moving to an Anthropic API key is a config change, whether because of volume, terms, or the CLI's bare-mode default changing |
| Subscription usage | **Daily cap** on work units run, default 10 | Keeps unattended use at individual scale |
| Model for Hermes and `model-router` | The operator's **OpenAI key** with **`gpt-6-luna`** | Already available; the subscription cannot cover Hermes; cheapest current OpenAI text model ($0.10 / $0.50 per million tokens), supports function calling. Step up to `gpt-6.1-terra` if the planner misreads requests |
| Agent permission mode | **`bypassPermissions`**, as a non-root user, with turn and tool limits | The only Claude Code mode that runs arbitrary shell commands unprompted; in print mode anything else that needs approval is denied |
| Worker network | `dev-worker` only on a new **internal-only network** (`helm-dev`), with egress through an allowlisting proxy; no host port | Claude Code's docs restrict bypass mode to isolated containers and say it gives no protection against prompt injection |
| Worker API auth | **Bearer key** (`DEV_WORKER_API_KEY`) on every endpoint except `/health` | Stops the agent, or any other container, from publishing work units |
| Paperclip and dev work | Work units are **never mirrored** as Paperclip issues; Hermes agent keeps timer heartbeat off, wake on demand on | Paperclip has its own task checkout, and any assignment or comment on a Paperclip task wakes the agent |
| Notifications | `dev-worker` calls the **Telegram API directly** | Fixed event messages need no model call and should not be paraphrased |
| Agent isolation | Agent runs as a **separate Unix user** with a scrubbed environment, in a **copy** of the clone; the worker diffs and pushes from its own pristine clone | The agent runs model-chosen shell commands next to the GitHub and Telegram tokens; a scrubbed environment alone leaves `/proc/<pid>/environ` and git hooks open |
| Mechanical-only validation | **Per-repo opt-in** in the allowlist; a request can add gates but never remove them | Lets low-risk repos skip the review gate without weakening the default |
| Worker identity | A **dedicated GitHub machine account** PAT for assignee actions | GitHub Lite human validation needs an `APPROVED` review from someone who is neither PR author nor assignee, so the operator cannot be both worker and reviewer |
| Authority identity | Existing optional **GitHub App** env for `publish` / `record-outcome` | Already supported in M4 |
| Default validation mode | **`both`** (mechanical, then human) | Unattended agents on the operator's own repos; nothing merges without a review |
| Planner | **Hermes** builds the request; `dev-worker` builds and hashes the `WorkUnit` | Keeps schema and hashing in TypeScript next to the protocol; Hermes only sends plain fields |
| Repo scope | **Allowlist** in `config/dev-worker/repos.yaml` with per-repo default checks | Prevents a mis-parsed message from publishing work to an arbitrary repo |

## Architecture

```mermaid
flowchart TD
    U[Operator on Telegram] --> H[Hermes]
    P[Paperclip routines] --> H
    H -->|POST /v1/work-units| W[dev-worker]
    H -->|GET /v1/status| W
    PA[personal-assistant] -->|GET /v1/status| W
    W -->|publish, claim, submit| GH[GitHub issue + PR]
    W -->|run| A[adapter-claude-code in temp clone]
    GH --> CI[Actions: unimatrix-mechanical + record-outcome]
    U -->|PR review| GH
    W -->|event messages| TG[Telegram API]
    W -.->|all egress| X[dev-egress-proxy]
```

Network layout:

- `compose.yaml` gains a second network, `helm-dev`, declared `internal: true`.
- `dev-worker` joins **only** `helm-dev`, so it has no direct route to the internet or to services that are only on `helm` (Paperclip, Decider, `decision-gateway`, `model-router`).
- `dev-egress-proxy` joins `helm-dev` and `helm`. It is the worker's only way out and forwards `CONNECT` requests to allowlisted hostnames without intercepting TLS, so no extra CA certificate is needed.
- `hermes` and `personal-assistant` join `helm-dev` in addition to `helm`, so they can resolve `dev-worker:8084`.
- `dev-worker` publishes no host port (Docker does not publish ports for containers on internal-only networks). Like Decider, it is probed with `docker compose exec`.

Coupling rules (additions to `docs/architecture.md`):

- Only `dev-worker` talks to GitHub for dev work and only it holds GitHub credentials.
- Hermes and `personal-assistant` reach dev work only through `dev-worker`'s HTTP API.
- `dev-worker` clones into its own volume. Still no Docker socket mounts and no host filesystem mounts.
- Dev work units live only in GitHub. Nothing creates, assigns or comments on Paperclip issues for them, because either action wakes the Hermes agent. Paperclip issues continue to exist only for routine firings such as the daily brief.
- The Hermes agent in Paperclip runs with timer heartbeat off and wake on demand on (Paperclip's default and recommended combination).

## Changes in Unimatrix

Shipped as an M5 milestone in that repo; Helm depends on all three.

### 1. Adapter selection and shared run flow

- Extract the adapter-neutral part of `runCursorWork` (clone → `startSha` → prompt → `git add -A` → binary cached diff) so adapters only supply a prompt function. The existing shape `{ cwd, instructions, apiKey }` changes so that `apiKey` is optional: each adapter resolves its own credential.
- The shared flow gains an optional **isolated work tree** mode, which Helm turns on:
  - The clone stays in a directory the agent cannot write to. The agent gets a copy of it (with its own `.git`, tokenless remote) as `cwd`.
  - After the agent exits, the flow never runs git inside the agent's copy. It computes the patch with the pristine clone's git directory pointed at the agent's work tree (`--git-dir` / `--work-tree`), with hooks and `core.fsmonitor` disabled, then applies the patch to the pristine clone and pushes from there.
  - Anything the agent wrote under its own `.git` (hooks, config, credential helpers) is therefore never executed or read by the token-holding process.
- CLI and library entry points take an adapter id (`--adapter cursor|claude-code`, default `cursor`) instead of hard-wiring `createSdkPrompt` and `CURSOR_API_KEY` in `apps/cli/src/github-flow.ts`. `CURSOR_API_KEY` is required only when the Cursor adapter is selected.
- Capability strings: `adapter:cursor`, `adapter:claude-code`. A client advertises the adapters it has configured.

### 2. `@unimatrix/adapter-claude-code`

- Spawns the installed `claude` binary in print mode (`claude -p`) with the working directory as `cwd` and the work unit's instructions written to **stdin**, so instructions that start with `-` are never parsed as flags. No Agent SDK dependency.
- Authentication is whatever the CLI finds in its environment. The adapter passes no key and never reads or logs the token. Intended use is `CLAUDE_CODE_OAUTH_TOKEN`; an `ANTHROPIC_API_KEY` also works for anyone who prefers metered billing.
- Must **not** pass `--bare` when the host selects subscription auth: bare mode never reads OAuth credentials.
- Takes an explicit environment for the subprocess instead of inheriting the parent's. The host passes only what the agent needs: `PATH`, `HOME`, the one Claude credential in use, and any proxy variables (`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`).
- Takes an optional launcher prefix (for example `["sudo", "-n", "/usr/local/bin/run-agent"]`) so the host can run the agent as a different Unix user. With a launcher set, the launcher is responsible for starting `claude`, and the adapter and launcher follow this contract:
  - **Arguments.** The adapter invokes `<launcher...> <timeoutSeconds> <claude flags...>`.
  - **Environment.** The adapter sets the explicit environment above on the launcher process and nothing else. The launcher must carry the credential and proxy variables across to `claude`; one that changes user may substitute its own `PATH` and `HOME`. Credentials never go in arguments, where other processes could read them.
  - **Exit status.** `124` means the run timed out. `125` means the launcher itself failed (bad arguments, a missing binary, could not switch user). Any other status is `claude`'s own.
- Takes a wall-clock `timeoutSeconds`. How it is enforced depends on whether a launcher is set:
  - **No launcher (agent runs as the adapter's own user).** The adapter starts the agent in its own process group and on expiry signals the group (`SIGTERM`, then `SIGKILL` after a grace period).
  - **With a launcher (agent runs as another user).** The adapter cannot signal the agent: an unprivileged process may not signal another user's processes, and `SIGKILL` sent to the launcher is not relayed. Enforcement is therefore the host's job. The adapter passes `timeoutSeconds` to the launcher and treats exit status `124` as a timeout. A launcher that is itself killed by a signal, or exits `137`, is an ordinary failure, not a timeout (an out-of-memory kill looks the same).
- Takes an optional `reaper` command that kills anything the agent left running. The adapter runs it exactly once per run, after the launcher has exited (or the backstop below has fired) and **before** the diff is computed, so leftover processes cannot change the work tree while it is read. It is never run from a late exit handler.
- Keeps a backstop timer of `timeoutSeconds` plus `backstopGraceSeconds` (default `60`; must be longer than the launcher's own `SIGTERM`-to-`SIGKILL` window). If the launcher has not exited by then, the adapter runs the `reaper` and waits up to 30 seconds more for the launcher to exit.
- Reports the host as **unsafe** when the reaper fails, or when the launcher is still alive after the backstop and reaper. The adapter never returns while a launcher it started is still running without saying so. An unsafe result releases the unit and tells the host not to start another run in this process.
- A timeout is reported as `failed`.
- After cloning with the tokenized URL, the shared run flow resets the clone's remote to the tokenless URL before the agent starts, so the GitHub token is not readable from `.git/config`. This applies to every adapter.
- Default invocation:

  ```text
  claude -p \
    --permission-mode bypassPermissions \
    --max-turns 50 \
    --disallowedTools "WebFetch" "WebSearch" \
    --output-format json \
    --no-session-persistence \
    < instructions
  ```

- `bypassPermissions` is the only mode that lets the agent run the project's own build and test commands without prompts. It is acceptable only under the host conditions listed in Helm's Security section; the adapter's README states them, and the CLI itself refuses this mode when run as root.
- Options exposed to the host: `maxTurns`, `disallowedTools`, `timeoutSeconds`, `backstopGraceSeconds`, `launcher`, `reaper`, and `maxBudgetUsd` (maps to `--max-budget-usd`; meaningful only with API-key auth).
- The JSON result is used only to tell success from a run error. The patch still comes from the git diff.
- `doctor` gains a check that `claude` can be started and can authenticate. It takes the same `launcher` and `reaper` options as a run and checks through them: `claude --version` via the launcher, the authentication check via the launcher (which proves the environment is carried across), and the reaper exiting `0`.
- Result mapping:
  - Binary missing, authentication failure, launcher failure (exit `125`) or an unsafe host → `released`. None of these consume an attempt.
  - Transient errors that say nothing about the work (subscription usage limit, rate limit, API overloaded, network or proxy failure) → `released`, with a `transient` reason and the limit's reset time when the CLI reports one. These do not consume an attempt.
  - Timeout, any other non-zero exit during the run, or an empty patch → `failed`.
- Must not import `provider-github` (existing rule).

### 3. Watch mode

- Library function plus CLI command `watch --repo owner/name [--repo ...] --adapter claude-code --interval 60`.
- Each tick: list open issues labelled `unimatrix`, reconstruct the snapshot, filter by capability match and availability, then run claim → run → submit for at most one unit at a time.
- Emits structured events (claimed, submitted with PR number, released with reason, failed with reason) so a host process can forward them.
- Takes an optional host callback that is asked before each claim and can decline it. Helm uses it for the daily cap and the usage-limit pause.
- On start, releases any assignment the client still holds from a previous process. Watch mode runs one unit at a time, so anything it holds at start-up is orphaned; releasing it avoids waiting out the lease.
- Stops claiming and returns an error to the host after an unsafe result or a launcher failure, instead of moving on to the next unit.
- Lease expiry and claim races are already handled by the provider; watch mode itself adds no new state. Any state behind the callback belongs to the host.

## Changes in Helm

### 1. `services/dev-worker`

Node service that imports the pinned Unimatrix build and runs the watch loop in-process. Its image also installs the Claude Code CLI at a pinned version.

The image has two non-root users. The service runs as `worker`, which owns the secrets and the pristine clones. The agent runs as `agent`. `agent` can write only to its per-run copy of the clone and its own `HOME`.

`worker` cannot signal `agent`'s processes, so starting and stopping the agent both go through `sudo`. The timer and the reaper must also be out of the agent's reach: a process running as `agent` could stop or kill them. Both therefore run as **root**, and only `claude` itself runs as `agent`.

Exactly two `sudo` rules exist, each letting `worker` run one fixed script as root and nothing else. Both scripts are owned by root, writable by neither user, call other binaries by absolute path, and do nothing in the working directory before dropping privileges:

| Script | Arguments | What it does |
|--------|-----------|--------------|
| `/usr/local/bin/run-agent` | `<seconds> <claude flags...>` | Runs `claude <flags...>` as `agent` under a root-owned `timeout --signal=TERM --kill-after=10 <seconds>`, and translates the result into the launcher exit statuses. The binary is always `claude`; the caller chooses only its flags. |
| `/usr/local/bin/reap-agent` | none | Sends `SIGKILL` to every process owned by `agent`, repeating until none remain. Exits non-zero if any are left after 20 seconds. Catches processes that left the process group (for example a build tool that daemonises). |

`run-agent` in detail:

- **Arguments.** `<seconds>` must be a whole number from `1` to `86400`. Zero (which `timeout` reads as "no limit"), fractions and anything else are rejected with exit `125`.
- **Environment.** The `sudo` rule for `run-agent` keeps exactly five variable names from the caller: `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `HTTPS_PROXY`, `HTTP_PROXY` and `NO_PROXY`. The script starts `claude` with a clean environment made of those plus a fixed `PATH` and `HOME` for `agent`. The credential is never an argument.
- **Privilege drop.** `claude` is started with `setpriv` as `agent` (user, group and supplementary groups) with `no_new_privs` set, so nothing the agent runs can use `sudo` or a setuid binary.
- **Exit status.** `124` when `timeout` reports a timeout, or reports a kill (`137`) at or after `<seconds>` have elapsed. `125` for the script's own failures, including `timeout`'s `125`–`127`. Otherwise `claude`'s status, so a `137` before the limit (for example an out-of-memory kill) stays an ordinary failure.

`dev-worker` passes `run-agent` as the adapter's `launcher` and `reap-agent` as its `reaper`.

Process lifecycle:

- Compose sets `init: true` for `dev-worker` and a `pids_limit`. When the worker process exits, the container stops and every process in it dies, so a restart always begins with no `agent` processes. There is no start-up reap.
- On an unsafe result (the reaper failed, or `run-agent` outlived the backstop), the worker sends a Telegram message and exits non-zero. `restart: unless-stopped` brings up a clean container.
- At start-up the worker runs `doctor` through the launcher and reaper. If that fails, it stays up with `GET /v1/status` reporting `status: "error"` and does not claim. A launcher failure during a run (exit `125`) puts it in the same state until `doctor` passes again, so a misconfigured host does not loop through the queue.
- At start-up watch mode releases any assignment left over from the previous process.

All endpoints except `/health` require `Authorization: Bearer $DEV_WORKER_API_KEY`; a missing or wrong key returns `401`. Hermes and `personal-assistant` receive the key from compose. The agent does not.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Compose healthcheck, same convention as other services |
| `POST /v1/work-units` | Build, hash, validate and publish a `WorkUnit`; returns `{ repo, issue, workUnitId }` |
| `GET /v1/status` | Summary across allowlisted repos, from reconstructed snapshots |

`POST /v1/work-units` request:

```json
{
  "repo": "xbonell/foo",
  "instructions": "Add retry with backoff to the weather client.",
  "validation": "both",
  "criteria": "Change is limited to the weather client and its tests."
}
```

- `repo` must be in the allowlist, otherwise `403`.
- `checks` always come from the repo's allowlist entry. The request cannot set them; a `checks` field is rejected with `422`.
- `validation` defaults to the repo's allowlist entry, or `both` when the entry sets none. The entry is a floor: a request may add a gate (`mechanical` → `both`) but one that drops a gate the entry requires is rejected with `422`.
- `criteria` is required for `human` and `both`.
- Publishing is never blocked by the daily cap. Once `DEV_WORKER_MAX_UNITS_PER_DAY` runs have started that day (`Europe/Madrid`), the watch loop stops claiming and remaining units stay `queued` until the next day. Runs released as `transient` are not counted.
- When a run is released for a usage limit, the worker stops claiming until the reset time the CLI reported, or for one hour if it reported none.
- The day's run count and the pause-until time are kept in `data/dev-worker/state.json` (a bind mount like other services' state), so a restart does not reset them.
- Each run has a wall-clock limit, `DEV_WORKER_RUN_TIMEOUT_SECONDS` (default `1800`). It must be a positive whole number and at least 300 seconds below `leaseDuration`. The margin covers the kill window (10 s), the backstop grace (60 s), the reaper and the wait after it (50 s), and the diff and push, so a run always ends while its lease is still valid. The worker checks this at start-up and refuses to start otherwise.
- Policy defaults: `maxAttempts: 2`, `maxConcurrentAssignments: 1`, `leaseDuration: 3600`.

`GET /v1/status` response:

```json
{
  "status": "ok",
  "notifications": "ok",
  "units": [
    {
      "repo": "xbonell/foo",
      "issue": 41,
      "title": "Add retry with backoff to the weather client.",
      "state": "awaiting_review",
      "pull": 42
    }
  ]
}
```

`state` is one of `queued`, `running`, `awaiting_checks`, `awaiting_review`, `validated`, `rejected`, `failed`, derived from the assignment status and recorded outcomes.

Status and error rules follow the calendar pattern: missing GitHub or model credentials → `status: "unconfigured"` with an empty list; GitHub failure → `status: "error"` plus a short safe `error` string with no tokens.

### 2. Notifications

`dev-worker` sends one fixed-format Telegram message per watch event (PR opened, run failed, validation recorded, usage-limit pause started, daily cap reached) by calling the Telegram `sendMessage` API directly. No model is involved. Failure to notify never fails the run.

Hermes' Telegram configuration stays in `data/hermes/.env`, as `.env.example` requires, and `dev-worker` does not read that file (it also holds Hermes' other secrets). The worker has its own variables in the root `.env`, `DEV_WORKER_TELEGRAM_BOT_TOKEN` and `DEV_WORKER_TELEGRAM_CHAT_ID`, which the operator sets to the same bot token and home channel.

Notifications are optional, but their absence is visible:

- With either variable unset, `dev-worker` logs a warning at startup and `GET /v1/status` reports `"notifications": "unconfigured"` (otherwise `"ok"`, or `"error"` after a failed send).
- `scripts/healthcheck.sh` warns when notifications are unconfigured, and when the worker's bot token differs from `TELEGRAM_BOT_TOKEN` in `data/hermes/.env`.
- `scripts/bootstrap.sh` copies the two values from `data/hermes/.env` into the root `.env` when they are set there and missing in the root file.

### 3. Planner (Hermes)

A Hermes skill, seeded by `scripts/bootstrap.sh`, that:

1. Recognises a development request and extracts `repo` and `instructions`.
2. Asks one clarifying question if the repo is missing or not allowlisted.
3. Calls `POST http://dev-worker:8084/v1/work-units` with the bearer key and replies with the issue link.

The skill does not call Decider. The Decider `development` candidate stays unhandled; wiring routing decisions to this lane is left to a later spec.

### 4. Daily brief

- `personal-assistant` calls `GET /v1/status` and adds `sections.dev` and `sections.dev_status`.
- Brief generation must not fail because `dev-worker` is down.
- The Hermes routine description gains a "Dev" block listing units in `awaiting_review`, `failed` and `rejected`. Mocked `priorities` stay until a separate spec replaces them.

### 5. Config

| Variable | Service | Purpose |
|----------|---------|---------|
| `DEV_WORKER_PORT` | dev-worker | Default `8084`; reachable only on the `helm-dev` network, not published on the host |
| `DEV_WORKER_API_KEY` | dev-worker, hermes, personal-assistant | Bearer key for the worker's API; required for compose, generated by `scripts/bootstrap.sh` |
| `UNIMATRIX_REF` | dev-worker build | Git SHA of `xbonell/unimatrix` to build |
| `GITHUB_TOKEN` | dev-worker | Machine-account PAT for claim, push and PR |
| `UNIMATRIX_GITHUB_APP_ID`, `UNIMATRIX_GITHUB_APP_INSTALLATION_ID`, `UNIMATRIX_GITHUB_APP_PRIVATE_KEY` | dev-worker | Authority for publish and outcome recording |
| `CLAUDE_CODE_OAUTH_TOKEN` | dev-worker | Subscription token for the Claude Code CLI, generated once with `claude setup-token` on the operator's machine; expires after one year |
| `CLAUDE_CODE_OAUTH_TOKEN_ISSUED` | healthcheck script | Date the token was generated (`YYYY-MM-DD`), used for the expiry warning |
| `CLAUDE_CODE_VERSION` | dev-worker build | Claude Code CLI version to install |
| `DEV_WORKER_INTERVAL_SECONDS` | dev-worker | Watch tick, default `60` |
| `DEV_WORKER_MAX_TURNS` | dev-worker | Agent turn limit per run, default `50` |
| `DEV_WORKER_MAX_BUDGET_USD` | dev-worker | Per-run spend cap; applied only when `DEV_WORKER_AUTH=api_key` |
| `DEV_WORKER_RUN_TIMEOUT_SECONDS` | dev-worker | Wall-clock limit per run, default `1800`; positive whole number, at least 300 below the lease duration |
| `DEV_WORKER_EGRESS_ALLOW` | dev-egress-proxy | Extra hosts the worker may reach, comma-separated, on top of the built-in list |
| `DEV_WORKER_AUTH` | dev-worker | `subscription` (default) or `api_key` |
| `DEV_WORKER_ANTHROPIC_API_KEY` | dev-worker | Anthropic key, used only when `DEV_WORKER_AUTH=api_key` |
| `DEV_WORKER_MAX_UNITS_PER_DAY` | dev-worker | Daily cap on runs started, default `10` |
| `DEV_WORKER_TELEGRAM_BOT_TOKEN`, `DEV_WORKER_TELEGRAM_CHAT_ID` | dev-worker | Direct event notifications; optional, same values as Hermes' bot token and home channel |

In non-interactive mode the CLI always prefers an API key over the subscription token, so a stray key would silently switch the worker to metered billing. Two rules prevent that:

- `compose.yaml` does not pass the stack-wide `ANTHROPIC_API_KEY` into `dev-worker`; the worker's key has its own name.
- `dev-worker` builds the agent's environment from `DEV_WORKER_AUTH`: in `subscription` mode the only credential the agent sees is `CLAUDE_CODE_OAUTH_TOKEN`; in `api_key` mode it is the key, exported to the agent as `ANTHROPIC_API_KEY`. The agent never sees the GitHub, Telegram or worker API credentials in either mode.

Besides its one credential, the agent's environment holds `PATH`, `HOME`, and the proxy variables `HTTPS_PROXY` and `HTTP_PROXY` (both `http://dev-egress-proxy:3128`) and `NO_PROXY=localhost,127.0.0.1`. Without them neither the CLI nor the agent's own `npm` and `git` commands can leave the internal network. The worker process uses the same proxy for GitHub and Telegram.

Hermes and `model-router` use the operator's OpenAI key. Hermes reads `OPENAI_API_KEY` (already passed by compose). `model-router` does not read that variable, and its base URL defaults to OpenRouter, so the operator's `.env` sets all four of its variables, replacing the stub default:

```text
MODEL_PROVIDER=openai_compatible
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=<the OpenAI key>
MODEL_NAME=gpt-6-luna
```

Hermes' model is set to `gpt-6-luna` in `data/hermes/config.yaml`.

The token goes in the gitignored root `.env`; `.env.example` documents the name only. `scripts/healthcheck.sh` warns when the token is within 30 days of expiry (the operator records the issue date in `CLAUDE_CODE_OAUTH_TOKEN_ISSUED`).

`config/dev-worker/repos.yaml`:

```yaml
repos:
  - repo: xbonell/foo
    checks:
      - id: unimatrix-mechanical
        type: command
        params: { command: pnpm, args: [test] }
  - repo: xbonell/scratchpad
    validation: mechanical   # opt-in: no review gate for this repo
    checks:
      - id: unimatrix-mechanical
        type: command
        params: { command: pnpm, args: [test] }
```

Each allowlisted repo needs the `unimatrix-mechanical` workflow installed and the machine account added as a collaborator. `scripts/healthcheck.sh` gains a "Dev worker" line, probed with `docker compose exec` as for Decider; a new `scripts/smoke-dev-worker.sh` runs `doctor` against each allowlisted repo, with the same launcher and reaper the service uses.

## Security

- Unimatrix's hard constraint holds: model credentials stay on the machine that executes the work, which here is the Helm host.
- The subscription token is used only by the unmodified Claude Code CLI, for the operator's own work. It is never handed to Hermes, Paperclip or any other service, and Helm never routes anyone else's requests through it.
- The worker shares the operator's subscription usage limits. One unit at a time, the `maxAttempts: 2` default and the daily cap keep unattended use modest. A usage-limit hit releases the unit without consuming an attempt, and `dev-worker` stops claiming until the limit resets (one hour if the CLI gives no reset time).
- The agent runs repo code and model-chosen shell commands inside the `dev-worker` container. The container gets no other service's secrets, no Docker socket, and a throwaway clone directory per run.
- Inside the container, the agent is isolated from the worker's own secrets in three ways:
  - **Separate user.** The agent runs as `agent`, the service as `worker`. A different UID cannot read the worker's `/proc/<pid>/environ` or memory, its state file, or the pristine clones.
  - **Scrubbed environment.** The agent's environment holds only its Claude credential, `PATH`, `HOME` and the proxy variables.
  - **No git in agent-written directories.** The agent works in a copy of the clone with a tokenless remote. The worker computes the diff from its own git directory with hooks and `core.fsmonitor` disabled, and pushes from the pristine clone, so hooks or git config planted by the agent never run in the token-holding process. Pushing and PR creation happen after the agent has exited.
- The worker's API requires a bearer key the agent does not have, so the agent cannot publish work units through `localhost:8084`.
- The request cannot weaken a repo's validation mode or supply checks, so neither a misread Telegram message nor another container can remove the review gate or choose the command CI runs.
- The agent runs in `bypassPermissions` mode, so three host conditions are mandatory:
  - **Non-root.** The service and the agent both run as non-root users (the CLI refuses bypass mode as root). Root exists in the container only inside the two fixed scripts, `run-agent` and `reap-agent`, which `worker` reaches through `sudo`. `worker` controls only a validated number, five named environment variables, and flags for a `claude` process that has already dropped to `agent`. `agent` has no `sudo` rule and runs with `no_new_privs`.
  - **Egress allowlist.** `dev-worker` is attached only to the internal `helm-dev` network and reaches the internet through `dev-egress-proxy`. Built-in hosts: `api.anthropic.com`, `github.com`, `api.github.com`, `api.telegram.org` and `registry.npmjs.org`; `DEV_WORKER_EGRESS_ALLOW` adds registries a repo needs. Everything else is refused, which limits what a prompt-injected agent could send out.
  - **Bounded runs.** A wall-clock timeout and a reaper that both run as root, so the agent cannot stop, kill or outlive them; the reaper clears leftover `agent` processes after every run, and the worker restarts the container if it cannot. Also `--max-turns`, a `pids_limit`, no web fetch or search tools, and no session persistence.
- The allowlist reduces but does not remove exfiltration risk: the agent can still reach GitHub and Telegram hosts through the proxy, can reach Hermes and `personal-assistant` on `helm-dev` (Hermes' API needs a key the agent lacks), and holds its own Claude credential. That is the accepted residual risk for unattended runs on the operator's own repos.
- The machine-account PAT is scoped to the allowlisted repos only. It cannot approve its own PRs, so `both` and `human` modes always need the operator.
- Instructions arriving over Telegram are limited by Hermes' existing `TELEGRAM_ALLOWED_USERS` allowlist.
- Tokens are redacted from errors and never written to issues, comments or Telegram (existing `redactSecret` behaviour).

## Out of scope

- Merging the two repositories or porting either to the other's language.
- A Paperclip provider for Unimatrix, or the Unimatrix "Full" server.
- Automatic merging of validated PRs.
- An `adapter-opencode` (or Codex) adapter. It is the intended second adapter, giving a coding path that does not depend on Anthropic, but it comes after milestone 1's adapter selection is in place.
- Splitting one request into several work units, or running units in parallel.
- Replacing the mocked priorities, fitness and news sections.

## Milestones

| # | Repo | Deliverable | Done when |
|---|------|-------------|-----------|
| 1 | unimatrix | Adapter selection, isolated work tree mode + `adapter-claude-code` | `claim-run-submit --adapter claude-code` opens a PR with no Cursor installed and no API key set; a hook planted in the agent's copy does not run; with a fake launcher, exit `124` is reported as a timeout, exit `125` releases the unit without using an attempt, a launcher that never exits triggers the backstop and an unsafe result, and the reaper runs exactly once in each case |
| 2 | unimatrix | `watch` | A published unit is picked up and submitted with no further commands |
| 3 | helm | `dev-worker` service with `helm-dev` network, egress proxy, API key, config, healthcheck, smoke script | `POST /v1/work-units` on a test repo ends in an open PR with a passing mechanical check; a request to a non-allowlisted host from inside the container is refused; `doctor` passes through the launcher; a run that ignores `SIGTERM` past the timeout is killed and reported as a timeout; a child started with `setsid` is gone after the run; as `agent`, signalling the `timeout` or `reap-agent` process fails with a permission error |
| 4 | helm | Hermes planner skill + Telegram notifications | A Telegram message produces a PR link reply |
| 5 | helm | `sections.dev` in the daily brief | Brief lists a PR awaiting review; brief still succeeds with `dev-worker` stopped |

## Resolved questions

| Question | Resolution |
|----------|------------|
| Paperclip overlap | GitHub stays the source of truth regardless of what Paperclip offers for tasks |
| Bare-mode default | Pin `CLAUDE_CODE_VERSION`; `DEV_WORKER_AUTH=api_key` is the fallback |
| Subscription terms | Start on the subscription with the daily cap; move to an API key if volume grows |
| Model for Hermes | Operator's OpenAI key with `gpt-6-luna`, also for `model-router` |
| Paperclip conflict | None, provided dev work is never mirrored into Paperclip and the Hermes agent keeps timer heartbeat off |
| CLI permission flags | `bypassPermissions` as a separate non-root user behind an egress allowlist, with time, turn and tool limits |
| Machine account | Create one; `both` stays the default, mechanical-only is a per-repo opt-in |
| Notification path | Direct Telegram call from `dev-worker` |

## Remaining checks

These do not block the design but should be done before or during implementation.

1. **Hermes heartbeat setting.** Look at the Hermes agent in the running Paperclip instance and confirm timer heartbeat is off and wake on demand is on. The docs describe this as the default; the instance itself has not been inspected.
2. **Egress proxy.** Choose the allowlisting proxy (it must filter `CONNECT` by hostname without TLS interception) and confirm that the Claude Code CLI, `git` and the package manager in the image all honour the proxy variables. This is the one piece of the design with no existing pattern in Helm.
3. **`gpt-6-luna` as planner.** OpenAI recommends it for cost-sensitive, high-volume work but does not rate it for tool calling. Milestone 4 should test it on a handful of real requests before it is relied on.
4. **Flag names at the pinned version.** The flags above are from the Claude Code docs as of 2026-11-13; re-check them when `CLAUDE_CODE_VERSION` is chosen, along with reading the prompt from stdin.
5. **Transient-error detection.** Confirm how the pinned CLI reports a usage limit and its reset time in `--output-format json`, so the adapter can tell it from a real run failure.
6. **Agent tooling as a second user.** Confirm the repo's build and test commands work as `agent` in the copied work tree (file ownership, package-manager caches under the agent's `HOME`).
7. **Launcher tooling in the image.** Confirm the base image ships GNU `timeout` (BusyBox's takes different options) and `setpriv`, and that the instructions on stdin reach `claude` through `sudo`, `timeout` and `setpriv`. The kill and reap behaviour itself is part of milestone 3's "done when".
8. **Releasing a held assignment.** Confirm the GitHub Lite provider lets the assignee release its own `running` assignment, which watch mode's start-up release depends on.

