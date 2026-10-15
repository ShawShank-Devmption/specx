/**
 * Turns one run's observations into the verdict body: which clauses are evaluated (contracts/sandbox_api.md
 * §2), the status precedence (§3), violation signatures and categories, and the effect diff.
 */
import { check, dbDelta, normaliseObserved, type RunContext } from "../contracts/checkers.js";
import type { AuditRow, Clause, ClauseResult, DbSnapshot, EffectDiff, EventRecord, Mode, ToolContract, VerdictStatus, Violation, ViolationCategory } from "../contracts/types.js";

export interface Evaluation {
  clause_results: ClauseResult[];
  violations: Violation[];
  status: VerdictStatus;
}

type Role = "pre" | "post" | "inv";

function category(clause: Clause, role: Role): ViolationCategory {
  if (role === "pre") return "precondition";
  switch (clause.kind) {
    case "at_most_once":
      return "race";
    case "no_unapproved_endpoint":
      return "unapproved_endpoint";
    case "no_third_party":
      return "third_party";
    case "storage_untouched":
      return "storage";
    default:
      return role === "inv" || clause.clause_id.startsWith("post_frame_") ? "side_effect" : "postcondition";
  }
}

async function evalAll(clauses: Clause[], role: Role, ctx: RunContext): Promise<{ clause: Clause; role: Role; result: ClauseResult }[]> {
  const out = [];
  for (const clause of clauses) {
    const o = await check(clause, ctx, role === "pre" ? "pre" : "post");
    const result: ClauseResult = { clause_id: clause.clause_id, kind: clause.kind, surface: clause.surface, passed: o.passed };
    if (o.observed !== undefined) result.observed = o.observed;
    if (o.expected !== undefined) result.expected = o.expected;
    if (o.message !== undefined) result.message = o.message;
    out.push({ clause, role, result });
  }
  return out;
}

export async function evaluateRun(contract: ToolContract, ctx: RunContext, opts: { mode: Mode; handlerError: string | null }): Promise<Evaluation> {
  const pre = await evalAll(contract.preconditions, "pre", ctx);
  const runPost = opts.mode !== "concurrent" && opts.handlerError === null && pre.every((p) => p.result.passed === true);
  const post = runPost ? await evalAll(contract.postconditions, "post", ctx) : [];
  const inv = await evalAll(contract.invariants, "inv", ctx);
  const all = [...pre, ...post, ...inv];

  const violations: Violation[] = all
    .filter((x) => x.result.passed === false)
    .map(({ clause, role, result }) => ({
      clause_id: clause.clause_id,
      severity: clause.severity,
      signature: `${ctx.toolId}|${clause.clause_id}|${clause.kind}|${normaliseObserved(clause.kind, result.observed, clause.params)}`,
      category: category(clause, role),
    }));

  let status: VerdictStatus = "pass";
  if (violations.length > 0) status = "fail";
  else if (opts.handlerError !== null) status = "error";
  else if (all.some((x) => x.result.passed === null)) status = "unverifiable";
  return { clause_results: all.map((x) => x.result), violations, status };
}

export function buildEffectDiff(o: {
  events: EventRecord[];
  dbBefore: DbSnapshot;
  dbAfter: DbSnapshot;
  newAudit: AuditRow[];
  urlBefore: string;
  urlAfter: string;
}): EffectDiff {
  const statusById = new Map(o.events.filter((e) => e.kind === "network_response").map((e) => [e.data.request_id, e.data.status]));
  const network = o.events
    .filter((e) => e.kind === "network_request")
    .map((e) => {
      const status = statusById.get(e.data.request_id);
      return {
        method: String(e.data.method),
        url: String(e.data.url),
        ...(typeof status === "number" ? { status } : {}),
        approved: e.data.approved === true,
        third_party: e.data.third_party === true,
        phase: e.phase,
      };
    });
  const muts = o.events.filter((e) => e.kind === "dom_mutation");
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  const selectors = (key: string) => [...new Set(muts.filter((e) => n(e.data[key]) > 0).map((e) => String(e.data.target_selector)))];
  const auditCounts = new Map<string, number>();
  for (const a of o.newAudit) auditCounts.set(a.event, (auditCounts.get(a.event) ?? 0) + 1);
  return {
    db: dbDelta(o.dbBefore, o.dbAfter),
    network,
    dom: {
      mutations: muts.reduce((s, e) => s + n(e.data.added) + n(e.data.removed) + n(e.data.attr_changed) + n(e.data.text_changed), 0),
      added_selectors: selectors("added"),
      removed_selectors: selectors("removed"),
      url_before: o.urlBefore,
      url_after: o.urlAfter,
    },
    storage: o.events.filter((e) => e.kind === "storage").map((e) => ({ area: String(e.data.area), op: String(e.data.op), key: String(e.data.key) })),
    audit: [...auditCounts].map(([event, count]) => ({ event, count })),
  };
}
