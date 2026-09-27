#!/usr/bin/env node
/**
 * Idempotently ensure Personal Assistant project + Daily brief routine
 * with schedule 0 7 * * * Europe/Madrid assigned to Hermes Runtime.
 */
const { randomBytes, createHash, randomUUID } = require("crypto");
const { Client } = require("/app/node_modules/.pnpm/pg@8.18.0/node_modules/pg");

const COMPANY_ID = process.env.PAPERCLIP_COMPANY_ID;
const HERMES_ID = process.env.PAPERCLIP_HERMES_AGENT_ID;
const USER_ID = process.env.PAPERCLIP_BOARD_USER_ID;
const BASE = process.env.PAPERCLIP_API_URL || "http://127.0.0.1:3100";
const PROJECT_NAME = "Personal Assistant";
const ROUTINE_TITLE = "Daily brief";
const CRON = "0 7 * * *";
const TZ_NAME = "Europe/Madrid";

const DESCRIPTION = `Generate the Helm personal-assistant daily brief.

Steps (do these exactly):
1. Use the terminal tool (not execute_code) to run:
   curl -sS -m 60 -X POST http://personal-assistant:8083/v1/generate-daily-brief -H 'Content-Type: application/json' -d '{}'
2. Comment on this issue with: date, Decider route (routing.choice), weather for each entry in sections.weather.locations (name, condition/temp from data, narrative per location), and the priorities list — taken from that JSON response.
3. Mark this issue done via Paperclip API using \$PAPERCLIP_API_KEY from the environment (never invent or paste keys). Use this issue's id and this run's id from the wake payload:
   PAPERCLIP_API_BASE="\${PAPERCLIP_API_URL%/}"
   PAPERCLIP_API_BASE="\${PAPERCLIP_API_BASE%/api}"
   curl -sS -X PATCH "\$PAPERCLIP_API_BASE/api/issues/<ISSUE_ID>" \\
     -H "Authorization: Bearer \$PAPERCLIP_API_KEY" \\
     -H "X-Paperclip-Run-Id: <RUN_ID>" \\
     -H "Content-Type: application/json" \\
     -d '{"status":"done","comment":"Daily brief delivered from personal-assistant."}'

Do not invent a parallel brief. Do not use execute_code. Use the personal-assistant service response as the source of truth.`;

function hashBearerToken(token) {
  return createHash("sha256").update(token).digest("hex");
}

async function api(token, method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { raw: text.slice(0, 1000) };
  }
  if (!res.ok) {
    const err = new Error(`${method} ${path} -> ${res.status}`);
    err.body = json;
    throw err;
  }
  return json;
}

function asList(payload, keys) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  for (const k of keys) {
    if (Array.isArray(payload[k])) return payload[k];
  }
  return [];
}

(async () => {
  if (!COMPANY_ID || !HERMES_ID || !USER_ID) {
    throw new Error("PAPERCLIP_COMPANY_ID / HERMES / BOARD_USER_ID required");
  }

  const c = new Client({
    connectionString: "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip",
  });
  await c.connect();

  // Hermes must accept routine assignment wakes
  await c.query(
    `UPDATE agents
     SET runtime_config = jsonb_set(
       coalesce(runtime_config, '{}'::jsonb),
       '{heartbeat,wakeOnDemand}',
       'true'::jsonb,
       true
     ),
     updated_at = NOW()
     WHERE id = $1`,
    [HERMES_ID]
  );

  const token = `pcp_board_${randomBytes(24).toString("hex")}`;
  await c.query(
    `INSERT INTO board_api_keys (id, user_id, name, key_hash, created_at, expires_at)
     VALUES ($1,$2,$3,$4,NOW(), NOW() + interval '1 day')`,
    [randomUUID(), USER_ID, "helm-daily-brief-routine", hashBearerToken(token)]
  );

  // Project
  let projects = asList(await api(token, "GET", `/api/companies/${COMPANY_ID}/projects`), [
    "projects",
    "items",
    "data",
  ]);
  let project = projects.find((p) => p.name === PROJECT_NAME);
  if (!project) {
    project = await api(token, "POST", `/api/companies/${COMPANY_ID}/projects`, {
      name: PROJECT_NAME,
      description: "Personal assistant workflows (daily brief, etc.)",
      status: "in_progress",
      leadAgentId: HERMES_ID,
    });
    console.log("created_project", project.id);
  } else {
    console.log("using_project", project.id);
  }

  // Routine
  let routines = asList(await api(token, "GET", `/api/companies/${COMPANY_ID}/routines`), [
    "routines",
    "items",
    "data",
  ]);
  let routine = routines.find((r) => r.title === ROUTINE_TITLE);
  if (!routine) {
    routine = await api(token, "POST", `/api/companies/${COMPANY_ID}/routines`, {
      title: ROUTINE_TITLE,
      description: DESCRIPTION,
      assigneeAgentId: HERMES_ID,
      projectId: project.id,
      priority: "medium",
      status: "active",
      concurrencyPolicy: "coalesce_if_active",
      catchUpPolicy: "skip_missed",
    });
    console.log("created_routine", routine.id);
  } else {
    console.log("using_routine", routine.id);
    const detail = await api(token, "GET", `/api/routines/${routine.id}`);
    const baseRevisionId =
      detail.latestRevisionId || detail.baseRevisionId || detail.revisionId || null;
    const patch = {
      description: DESCRIPTION,
      assigneeAgentId: HERMES_ID,
      projectId: project.id,
      status: "active",
      concurrencyPolicy: "coalesce_if_active",
      catchUpPolicy: "skip_missed",
    };
    if (baseRevisionId) patch.baseRevisionId = baseRevisionId;
    try {
      routine = await api(token, "PATCH", `/api/routines/${routine.id}`, patch);
    } catch (e) {
      console.log("routine_patch_skipped", e.message, JSON.stringify(e.body || {}).slice(0, 300));
      routine = detail;
    }
  }

  const detail = await api(token, "GET", `/api/routines/${routine.id}`);
  const triggers = detail.triggers || [];
  let trigger = triggers.find(
    (t) =>
      t.kind === "schedule" &&
      t.cronExpression === CRON &&
      (t.timezone || "UTC") === TZ_NAME &&
      t.enabled !== false
  );
  if (!trigger) {
    trigger = await api(token, "POST", `/api/routines/${routine.id}/triggers`, {
      kind: "schedule",
      cronExpression: CRON,
      timezone: TZ_NAME,
      label: "Every morning 07:00",
      enabled: true,
    });
    console.log("created_trigger", trigger.id);
  } else {
    console.log("using_trigger", trigger.id);
  }

  await c.end();

  console.log(
    JSON.stringify(
      {
        ok: true,
        projectId: project.id,
        routineId: routine.id,
        triggerId: trigger.id,
        cron: CRON,
        timezone: TZ_NAME,
        assigneeAgentId: HERMES_ID,
        manualRun: `POST ${BASE}/api/routines/${routine.id}/run`,
      },
      null,
      2
    )
  );
})().catch((e) => {
  console.error("FATAL", e.message, e.body || e);
  process.exit(1);
});
