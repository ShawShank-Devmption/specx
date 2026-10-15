/** Builders for checker tests: a RunContext without a browser. */
import fs from "node:fs";
import type { RunContext } from "../../src/contracts/checkers.js";
import type { AppManifest, DbSnapshot, EventRecord } from "../../src/contracts/types.js";
import { manifestPath } from "../../src/paths.js";

export const shopManifest = JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest;

export function db(tables: Record<string, Record<string, unknown>[]>): DbSnapshot {
  return Object.fromEntries(Object.entries(tables).map(([t, rows]) => [t, { count: rows.length, rows }]));
}

let seq = 0;
export function ev(kind: EventRecord["kind"], data: Record<string, unknown>, phase: EventRecord["phase"] = "during"): EventRecord {
  return { session_id: "s", run_id: "r", seq: seq++, t_ms: seq, phase, kind, data };
}

export function req(method: string, path: string, extra: Record<string, unknown> = {}): EventRecord {
  return ev("network_request", { method, path, url: `http://127.0.0.1:5101${path}`, host: "127.0.0.1:5101", approved: true, third_party: false, ...extra });
}

export function ctx(over: Partial<RunContext> = {}): RunContext {
  const empty = db({ products: [{ id: 1, stock: 5 }], cart_items: [] });
  return {
    manifest: shopManifest,
    toolId: "shop.add_to_cart",
    args: {},
    output: null,
    user: { id: 1 },
    dbBefore: empty,
    dbAfter: empty,
    newAudit: [],
    events: [],
    dom: null,
    ...over,
  };
}
