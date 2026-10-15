// Test hooks every seed app exposes (contracts/sandbox_api.md). They act on the caller's tenant only.
import express from "express";
import { snapshot, tenantOf } from "./core.js";

const LEAK_KINDS = new Set(["delayed_post", "storage_write", "third_party_fetch", "background_poll"]);

export function createLeakState(pollPath) {
  const armed = new Map();
  return {
    arm(tenant, kind, delayMs) {
      if (kind === null) armed.delete(tenant);
      else armed.set(tenant, { kind, delayMs });
    },
    clear: (tenant) => armed.delete(tenant),
    /** Middleware: the next mutating API response of an armed tenant carries the telemetry header, once. */
    middleware(req, res, next) {
      const mutating = req.method !== "GET" && req.path.startsWith("/api/") && req.path !== "/api/login" && req.path !== "/api/analytics";
      const leak = mutating ? armed.get(tenantOf(req)) : undefined;
      if (leak) {
        res.setHeader("x-telemetry", `${leak.kind};${leak.delayMs};${pollPath}`);
        armed.delete(tenantOf(req));
      }
      next();
    },
  };
}

export function testHooks({ store, tables, leaks, applyState }) {
  const r = express.Router();
  r.post("/__test/reset", (req, res) => {
    const tenant = tenantOf(req);
    store.reset(tenant);
    leaks.clear(tenant);
    res.json({ ok: true });
  });
  r.get("/__test/db", (req, res) => res.json({ tables: snapshot(store.get(tenantOf(req)), tables) }));
  r.get("/__test/audit", (req, res) => {
    const since = Number(req.query.since ?? 0);
    const events = store.get(tenantOf(req)).prepare("SELECT * FROM audit_log WHERE id > ? ORDER BY id").all(since);
    res.json({ events: events.map((e) => ({ ...e })) });
  });
  r.post("/__test/leak", (req, res) => {
    const { kind, delay_ms: delayMs = 500 } = req.body ?? {};
    if (kind !== null && !LEAK_KINDS.has(kind)) return res.status(400).json({ error: `unknown leak kind ${kind}` });
    leaks.arm(tenantOf(req), kind, Number(delayMs));
    res.json({ ok: true });
  });
  r.post("/__test/apply", (req, res) => {
    applyState(store.get(tenantOf(req)), req.body?.state ?? {});
    res.json({ ok: true });
  });
  return r;
}
