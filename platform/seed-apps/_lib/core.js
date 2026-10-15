// Shared runtime for seed apps: per-tenant in-memory SQLite, cookie sessions, audit helper, JSON errors.
// Each sandbox session is a tenant (cookie `specx_tenant` or header `x-specx-tenant`), so parallel
// sessions never see each other's data. Reset = rebuild the tenant DB from schema.sql + seed.sql.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export function parseCookies(header) {
  const out = {};
  for (const part of (header ?? "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

export function tenantOf(req) {
  return req.get("x-specx-tenant") || parseCookies(req.headers.cookie).specx_tenant || "default";
}

export function createTenantStore(appDir) {
  const sql = ["schema.sql", "seed.sql"].map((f) => fs.readFileSync(path.join(appDir, f), "utf8")).join("\n");
  const dbs = new Map();
  const build = () => {
    const db = new DatabaseSync(":memory:");
    db.exec(sql);
    return db;
  };
  return {
    get(tenant) {
      if (!dbs.has(tenant)) dbs.set(tenant, build());
      return dbs.get(tenant);
    },
    reset(tenant) {
      dbs.get(tenant)?.close();
      dbs.set(tenant, build());
    },
  };
}

/** Cookie sessions: sid -> username. The user row is resolved per request in the caller's tenant DB. */
export function createAuth(cookieName) {
  const sessions = new Map();
  return {
    cookieName,
    login(res, username) {
      const sid = crypto.randomUUID();
      sessions.set(sid, username);
      res.cookie(cookieName, sid, { httpOnly: true, sameSite: "lax", path: "/" });
    },
    logout(req, res) {
      sessions.delete(parseCookies(req.headers.cookie)[cookieName]);
      res.clearCookie(cookieName, { path: "/" });
    },
    usernameOf(req) {
      return sessions.get(parseCookies(req.headers.cookie)[cookieName]) ?? null;
    },
  };
}

export function audit(db, event, actor, entity, entityId) {
  db.prepare("INSERT INTO audit_log (event, actor, entity, entity_id, ts) VALUES (?, ?, ?, ?, ?)").run(
    event,
    actor,
    entity,
    String(entityId),
    new Date().toISOString(),
  );
}

export function snapshot(db, tables) {
  const out = {};
  for (const t of tables) {
    const rows = db.prepare(`SELECT * FROM ${t} ORDER BY id`).all().map((r) => ({ ...r }));
    out[t] = { count: rows.length, rows };
  }
  return out;
}

/** Express error handler: JSON for API and test hooks, plain text for pages. */
export function jsonErrors(err, req, res, _next) {
  const status = err.status || err.statusCode || 500;
  if (req.path.startsWith("/api/") || req.path.startsWith("/__test/")) return res.status(status).json({ error: err.message });
  res.status(status).type("text").send(err.message);
}

export const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
