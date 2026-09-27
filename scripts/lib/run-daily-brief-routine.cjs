#!/usr/bin/env node
const { randomBytes, createHash, randomUUID } = require("crypto");
const { Client } = require("/app/node_modules/.pnpm/pg@8.18.0/node_modules/pg");

const COMPANY_ID = process.env.PAPERCLIP_COMPANY_ID;
const USER_ID = process.env.PAPERCLIP_BOARD_USER_ID;
const BASE = process.env.PAPERCLIP_API_URL || "http://127.0.0.1:3100";
const TITLE = process.env.PAPERCLIP_ROUTINE_TITLE || "Daily brief";
const WAIT = process.env.PAPERCLIP_WAIT !== "0";

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
  const c = new Client({
    connectionString: "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip",
  });
  await c.connect();
  const token = `pcp_board_${randomBytes(24).toString("hex")}`;
  await c.query(
    `INSERT INTO board_api_keys (id, user_id, name, key_hash, created_at, expires_at)
     VALUES ($1,$2,$3,$4,NOW(), NOW() + interval '1 day')`,
    [randomUUID(), USER_ID, "helm-daily-brief-run", hashBearerToken(token)]
  );

  let routineId = process.env.PAPERCLIP_ROUTINE_ID || "";
  if (!routineId) {
    const routines = asList(await api(token, "GET", `/api/companies/${COMPANY_ID}/routines`), [
      "routines",
      "items",
      "data",
    ]);
    const match = routines.find((r) => r.title === TITLE);
    if (!match) throw new Error(`Routine not found: ${TITLE}`);
    routineId = match.id;
  }

  const started = Date.now();
  const run = await api(token, "POST", `/api/routines/${routineId}/run`, {
    source: "manual",
  });
  const issueId =
    run.linkedIssueId ||
    run.linked_issue_id ||
    run.issueId ||
    run.issue_id ||
    run.issue?.id ||
    null;
  console.log(
    "routine_run",
    JSON.stringify(
      { id: run.id, status: run.status, issueId, rawKeys: Object.keys(run || {}) },
      null,
      2
    )
  );

  if (!WAIT) {
    await c.end();
    return;
  }

  // If API omitted the link, resolve from routine_runs after a short settle.
  let resolvedIssueId = issueId;
  if (!resolvedIssueId && run.id) {
    for (let i = 0; i < 10 && !resolvedIssueId; i++) {
      const row = await c.query(
        `SELECT linked_issue_id FROM routine_runs WHERE id=$1`,
        [run.id]
      );
      resolvedIssueId = row.rows[0]?.linked_issue_id || null;
      if (!resolvedIssueId) await new Promise((r) => setTimeout(r, 1000));
    }
  }

  let agentId = null;
  if (resolvedIssueId) {
    const issue = await c.query("SELECT assignee_agent_id FROM issues WHERE id=$1", [
      resolvedIssueId,
    ]);
    agentId = issue.rows[0]?.assignee_agent_id;
  }

  let last = null;
  for (let i = 0; i < 60; i++) {
    if (agentId) {
      const rows = await c.query(
        `SELECT id, status, error, error_code, created_at
         FROM heartbeat_runs
         WHERE agent_id=$1 AND created_at > to_timestamp($2)
         ORDER BY created_at DESC LIMIT 1`,
        [agentId, started / 1000 - 5]
      );
      last = rows.rows[0];
      console.log(
        `poll_${i}`,
        last?.status || "none",
        last?.error_code || "",
        last?.error ? String(last.error).slice(0, 120) : ""
      );
      if (last && ["succeeded", "failed", "cancelled", "timed_out"].includes(last.status)) break;
    } else {
      console.log(`poll_${i}`, "waiting_for_agent", "run=" + (run.id || ""));
    }
    await new Promise((r) => setTimeout(r, 3000));
  }

  if (resolvedIssueId) {
    const issue = await c.query("SELECT id, title, status FROM issues WHERE id=$1", [
      resolvedIssueId,
    ]);
    const comments = await c.query(
      `SELECT left(coalesce(body,''), 400) AS body FROM issue_comments WHERE issue_id=$1 ORDER BY created_at DESC LIMIT 3`,
      [resolvedIssueId]
    );
    console.log("issue", JSON.stringify(issue.rows[0], null, 2));
    console.log("comments", JSON.stringify(comments.rows, null, 2));
  }

  console.log("FINAL_RUN", JSON.stringify(last, null, 2));
  await c.end();
  if (!last || last.status !== "succeeded") process.exit(2);
})().catch((e) => {
  console.error("FATAL", e.message, e.body || e);
  process.exit(1);
});
