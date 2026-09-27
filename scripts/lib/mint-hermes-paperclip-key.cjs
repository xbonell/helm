#!/usr/bin/env node
/**
 * Mint a Paperclip agent API key for Hermes Runtime and print token once.
 * Used by scripts/ensure-hermes-paperclip-key.sh (never commit the token).
 */
const { randomBytes, createHash, randomUUID } = require("crypto");
const { Client } = require("/app/node_modules/.pnpm/pg@8.18.0/node_modules/pg");

const HERMES_ID = process.env.PAPERCLIP_HERMES_AGENT_ID;
const USER_ID = process.env.PAPERCLIP_BOARD_USER_ID;
const BASE = process.env.PAPERCLIP_API_URL || "http://127.0.0.1:3100";
const KEY_NAME = process.env.PAPERCLIP_KEY_NAME || "helm-hermes-paperclip";

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

(async () => {
  if (!HERMES_ID || !USER_ID) throw new Error("HERMES_AGENT_ID / BOARD_USER_ID required");

  const c = new Client({
    connectionString: "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip",
  });
  await c.connect();
  const boardToken = `pcp_board_${randomBytes(24).toString("hex")}`;
  await c.query(
    `INSERT INTO board_api_keys (id, user_id, name, key_hash, created_at, expires_at)
     VALUES ($1,$2,$3,$4,NOW(), NOW() + interval '1 day')`,
    [randomUUID(), USER_ID, "helm-mint-hermes-key", hashBearerToken(boardToken)]
  );

  const key = await api(boardToken, "POST", `/api/agents/${HERMES_ID}/keys`, {
    name: KEY_NAME,
  });
  const token = key.token || key.key || key.apiKey || null;
  if (!token) throw new Error("create key response missing token");
  // Single-line machine-readable for the shell wrapper
  console.log(`TOKEN=${token}`);
  console.log(`KEY_ID=${key.id}`);
  await c.end();
})().catch((e) => {
  console.error("FATAL", e.message, e.body || e);
  process.exit(1);
});
