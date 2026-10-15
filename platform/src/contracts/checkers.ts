/**
 * One checker per contract clause kind (contracts/README.md). Checkers are pure over a RunContext so they
 * are unit-testable without a browser; the sandbox builds the context from a real run.
 */
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import { patternMatches } from "./match.js";
import type { AppManifest, AuditRow, Clause, ClauseKind, DbSnapshot, EventRecord, RowDelta } from "./types.js";
import { resolveRef, rowMatches, type RefScope } from "./where.js";

/** The slice of a Playwright page the dom checkers need. */
export interface DomProbe {
  url(): string;
  count(selector: string): Promise<number>;
  text(selector: string): Promise<string>;
}

export interface RunContext extends RefScope {
  manifest: AppManifest;
  toolId: string;
  output: unknown;
  dbBefore: DbSnapshot;
  dbAfter: DbSnapshot;
  newAudit: AuditRow[];
  /** This run's events (during + post phases). */
  events: EventRecord[];
  dom: DomProbe | null;
  /** Present in concurrent mode: DB snapshots around the whole group. */
  group?: { dbBefore: DbSnapshot; dbAfter: DbSnapshot };
}

/** Preconditions read dbBefore; everything else reads dbAfter. */
export type When = "pre" | "post";

export interface Outcome {
  passed: boolean | null;
  observed?: unknown;
  expected?: unknown;
  message?: string;
}

type Params = Record<string, unknown>;
type Checker = (ctx: RunContext, p: Params, when: When) => Promise<Outcome> | Outcome;

export const USER_MENU = "[data-testid=user-menu]";
const ZERO: RowDelta = { inserted: 0, updated: 0, deleted: 0 };

export function dbDelta(before: DbSnapshot, after: DbSnapshot): Record<string, RowDelta> {
  const out: Record<string, RowDelta> = {};
  for (const table of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const b = new Map((before[table]?.rows ?? []).map((r) => [String(r.id), JSON.stringify(r)]));
    const a = new Map((after[table]?.rows ?? []).map((r) => [String(r.id), JSON.stringify(r)]));
    const d = { inserted: 0, updated: 0, deleted: 0 };
    for (const [id, row] of a) {
      if (!b.has(id)) d.inserted++;
      else if (b.get(id) !== row) d.updated++;
    }
    for (const id of b.keys()) if (!a.has(id)) d.deleted++;
    if (d.inserted || d.updated || d.deleted) out[table] = d;
  }
  return out;
}

function counterOk(expected: unknown, observed: number): boolean {
  if (typeof expected === "number") return observed === expected;
  if (expected !== null && typeof expected === "object") {
    const { min, max } = expected as { min?: number; max?: number };
    return (min === undefined || observed >= min) && (max === undefined || observed <= max);
  }
  return true;
}

const requests = (ctx: RunContext) => ctx.events.filter((e) => e.kind === "network_request");
const str = (v: unknown) => String(v ?? "");
const tableRows = (db: DbSnapshot, table: unknown) => db[str(table)]?.rows ?? [];
const outputValidators = new Map<string, ValidateFunction>();
const ajv = new Ajv2020({ strict: false });

function noDom(): Outcome {
  return { passed: null, message: "no page available to evaluate a dom clause" };
}

const CHECKERS: Record<ClauseKind, Checker> = {
  dom_exists: async (ctx, p) => (ctx.dom ? { passed: (await ctx.dom.count(str(p.selector))) > 0 } : noDom()),
  dom_absent: async (ctx, p) => (ctx.dom ? { passed: (await ctx.dom.count(str(p.selector))) === 0 } : noDom()),
  dom_text_contains: async (ctx, p) => {
    if (!ctx.dom) return noDom();
    const text = await ctx.dom.text(str(p.selector));
    return { passed: text.toLowerCase().includes(str(p.text).toLowerCase()), observed: text.slice(0, 200) };
  },
  url_matches: (ctx, p) => (ctx.dom ? { passed: new RegExp(str(p.pattern)).test(ctx.dom.url()), observed: ctx.dom.url() } : noDom()),
  auth_state: async (ctx, p) => {
    if (!ctx.dom) return noDom();
    const loggedIn = (await ctx.dom.count(USER_MENU)) > 0;
    return { passed: loggedIn === Boolean(p.logged_in), observed: loggedIn, expected: Boolean(p.logged_in) };
  },
  network_calls: (ctx, p) => {
    const n = requests(ctx).filter((e) => str(e.data.method) === str(p.method).toUpperCase() && patternMatches(str(p.path), str(e.data.path))).length;
    const min = typeof p.min === "number" ? p.min : 1;
    const max = typeof p.max === "number" ? p.max : 1;
    return { passed: n >= min && n <= max, observed: n, expected: [min, max] };
  },
  no_unapproved_endpoint: (ctx) => {
    const bad = requests(ctx)
      .filter((e) => e.data.third_party !== true && e.data.approved !== true)
      .map((e) => `${str(e.data.method)} ${str(e.data.path)}`);
    return { passed: bad.length === 0, observed: bad, expected: [] };
  },
  no_third_party: (ctx) => {
    const hosts = requests(ctx).filter((e) => e.data.third_party === true).map((e) => str(e.data.host));
    return { passed: hosts.length === 0, observed: hosts, expected: [] };
  },
  db_delta: (ctx, p) => {
    const observed = dbDelta(ctx.dbBefore, ctx.dbAfter)[str(p.table)] ?? ZERO;
    const expected = Object.fromEntries((["inserted", "updated", "deleted"] as const).filter((k) => k in p).map((k) => [k, p[k]]));
    const passed = Object.entries(expected).every(([k, v]) => counterOk(v, observed[k as keyof RowDelta]));
    return { passed, observed, expected };
  },
  db_row_exists: (ctx, p, when) => {
    const n = tableRows(when === "pre" ? ctx.dbBefore : ctx.dbAfter, p.table).filter((r) => rowMatches(r, (p.where ?? {}) as Params, ctx)).length;
    return { passed: n > 0, observed: n, expected: ">=1" };
  },
  db_no_row: (ctx, p) => {
    const hits = tableRows(ctx.dbAfter, p.table).filter((r) => rowMatches(r, (p.where ?? {}) as Params, ctx));
    return { passed: hits.length === 0, observed: hits.map((r) => r.id), expected: [] };
  },
  audit_event: (ctx, p) => {
    const n = ctx.newAudit.filter((a) => (p.event === undefined || a.event === p.event) && (p.entity === undefined || a.entity === p.entity)).length;
    const want = typeof p.count === "number" ? p.count : 1;
    return { passed: n === want, observed: n, expected: want };
  },
  storage_untouched: (ctx) => {
    const writes = ctx.events
      .filter((e) => e.kind === "storage" && ["set", "remove", "clear"].includes(str(e.data.op)))
      .map((e) => ({ area: str(e.data.area), op: str(e.data.op), key: str(e.data.key) }));
    return { passed: writes.length === 0, observed: writes, expected: [] };
  },
  at_most_once: (ctx, p) => {
    const snaps = ctx.group ?? ctx;
    const inserted = (dbDelta(snaps.dbBefore, snaps.dbAfter)[str(p.table)] ?? ZERO).inserted;
    return { passed: inserted <= 1, observed: inserted, expected: 1 };
  },
  output_matches: (ctx, p) => {
    const key = JSON.stringify(p.schema ?? {});
    let fn = outputValidators.get(key);
    if (!fn) {
      fn = ajv.compile((p.schema ?? {}) as object);
      outputValidators.set(key, fn);
    }
    const ok = fn(ctx.output);
    return ok ? { passed: true } : { passed: false, message: ajv.errorsText(fn.errors) };
  },
};

export async function check(clause: Clause, ctx: RunContext, when: When): Promise<Outcome> {
  const params = Object.fromEntries(Object.entries(clause.params).map(([k, v]) => [k, k === "where" || k === "schema" ? v : resolveRef(v, ctx)]));
  try {
    return await CHECKERS[clause.kind](ctx, params, when);
  } catch (err) {
    return { passed: null, message: `checker error: ${(err as Error).message}` };
  }
}

const stripIds = (s: string) =>
  s
    .replace(/\d{4}-\d{2}-\d{2}T[\d:.]+Z/g, ":ts")
    .replace(/\/\d+(?=\/|$|\?)/g, "/:n")
    .replace(/\?.*$/, "");
const uniqSorted = (xs: string[]) => [...new Set(xs)].sort().join(",");

/** Stable, id-free description of what a failed clause observed; the last part of a violation signature. */
export function normaliseObserved(kind: ClauseKind, observed: unknown, params: Params = {}): string {
  switch (kind) {
    case "db_delta": {
      const d = (observed ?? ZERO) as RowDelta;
      return `${str(params.table)} inserted=${d.inserted} updated=${d.updated} deleted=${d.deleted}`;
    }
    case "at_most_once":
      return `${str(params.table)} x${str(observed)}`;
    case "network_calls":
      return `${str(params.method)} ${str(params.path)} x${str(observed)}`;
    case "no_unapproved_endpoint":
    case "no_third_party":
      return uniqSorted(((observed ?? []) as string[]).map(stripIds));
    case "storage_untouched":
      return uniqSorted(((observed ?? []) as { area: string; op: string; key: string }[]).map((w) => `${w.area}:${w.op}:${w.key}`));
    case "audit_event":
      return `${str(params.event ?? params.entity)} count=${str(observed)}`;
    case "db_row_exists":
    case "db_no_row":
      return `${str(params.table)} where ${Object.keys((params.where ?? {}) as Params).sort().join(",")}`;
    case "url_matches":
      return stripIds(str(observed).replace(/^https?:\/\/[^/]+/, ""));
    case "auth_state":
      return `logged_in=${str(observed)}`;
    case "output_matches":
      return "invalid output";
    default:
      return str(params.selector);
  }
}
