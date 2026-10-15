/**
 * F1 contract deriver: turns code evidence (routes + SQL), the app manifest's declared invariants and the
 * tool's observed output schema into executable pre/postconditions and invariants. Rules are listed in
 * contracts/README.md ("Derivation rules used by F1"); every clause is mechanically checkable.
 */
import type { RouteEvidence, SqlStatement } from "../generator/repo.js";
import type { AppManifest, Clause, ToolContract, ToolDefinition, Where } from "./types.js";

type Counter = number | { min?: number; max?: number };

/** Maps a WHERE/insert column to a value reference, or null when the binding cannot be known statically. */
function refFor(col: string, params: Set<string>): string | null {
  if (params.has(col)) return `$args.${col}`;
  if (col === "user_id") return "$user.id";
  return null;
}

function whereFor(cols: string[], params: Set<string>): Where | null {
  if (cols.length === 0) return null;
  const where: Where = {};
  for (const c of cols) {
    const ref = refFor(c, params);
    if (ref === null) return null;
    where[c] = ref;
  }
  return where;
}

const byId = (s: SqlStatement) => s.whereCols.length === 1 && s.whereCols[0] === "id";

function tableForFk(col: string, manifest: AppManifest): string | null {
  const base = col.replace(/_id$/, "");
  return [`${base}s`, base].find((t) => manifest.tables.includes(t)) ?? null;
}

export function deriveContract(tool: Pick<ToolDefinition, "tool_id" | "risk_level" | "output_schema">, route: RouteEvidence, manifest: AppManifest): ToolContract {
  const params = new Set([...route.pathParams, ...route.bodyFields]);
  const clause = (id: string, surface: Clause["surface"], kind: Clause["kind"], p: Record<string, unknown>, description: string, severity: Clause["severity"]): Clause => ({
    clause_id: id,
    surface,
    kind,
    params: p,
    description,
    severity,
  });

  // ---------------------------------------------------------------- preconditions
  const pre: Clause[] = [clause("pre_logged_in", "aria", "auth_state", { logged_in: true }, "The user is logged in", "high")];
  const seen = new Set<string>();
  const addExists = (table: string, where: Where, severity: Clause["severity"], why: string) => {
    const key = JSON.stringify([table, where]);
    if (seen.has(key)) return;
    seen.add(key);
    let id = `pre_exists_${table}`;
    for (let n = 2; pre.some((c) => c.clause_id === id); n++) id = `pre_exists_${table}_${n}`;
    pre.push(clause(id, "db", "db_row_exists", { table, where }, why, severity));
  };
  for (const s of route.statements) {
    if (s.op === "INSERT" && !s.insertSelect) {
      for (const col of s.insertCols.filter((c) => c.endsWith("_id") && params.has(c))) {
        const table = tableForFk(col, manifest);
        if (table) addExists(table, { id: `$args.${col}` }, "medium", `Referenced ${table} row ${col} exists`);
      }
      continue;
    }
    const where = whereFor(s.whereCols, params);
    if (!where) continue;
    if (s.op === "UPDATE" || s.op === "DELETE") addExists(s.table, where, "high", `The ${s.table} row(s) to ${s.op.toLowerCase()} exist`);
    else if (s.op === "SELECT" && s.exec === "get") addExists(s.table, where, "medium", `The ${s.table} row being read exists`);
    else if (s.op === "INSERT" && s.sourceTable) addExists(s.sourceTable, where, "high", `Source ${s.sourceTable} rows exist`);
  }

  // ---------------------------------------------------------------- postconditions
  const post: Clause[] = [clause("post_one_call", "network", "network_calls", { method: route.method, path: route.path, min: 1, max: 1 }, `Exactly one ${route.method} ${route.path}`, "high")];
  for (const table of route.tablesWritten) {
    const counters: { inserted: Counter; updated: Counter; deleted: Counter } = { inserted: 0, updated: 0, deleted: 0 };
    for (const s of route.statements.filter((x) => x.table === table)) {
      if (s.op === "INSERT") counters.inserted = s.insertSelect ? { min: 1 } : 1;
      if (s.op === "DELETE") counters.deleted = byId(s) ? 1 : { min: 1 };
      if (s.op === "UPDATE") counters.updated = byId(s) ? { min: 0, max: 1 } : { min: 0 };
    }
    post.push(clause(`post_db_${table}`, "db", "db_delta", { table, ...counters }, `Row changes on ${table} match the route's SQL`, "high"));
  }
  for (const table of manifest.tables.filter((t) => t !== manifest.audit_table && !route.tablesWritten.includes(t))) {
    post.push(clause(`post_frame_${table}`, "db", "db_delta", { table, inserted: 0, updated: 0, deleted: 0 }, `${table} is untouched`, "high"));
  }
  if (tool.risk_level !== "read") {
    const p = route.auditEvent ? { event: route.auditEvent, count: 1 } : { entity: route.tablesWritten[0] ?? "unknown", count: 1 };
    post.push(clause("post_audit", "audit", "audit_event", p, "The change is audited exactly once", "medium"));
  }
  if (tool.output_schema) post.push(clause("post_output", "code", "output_matches", { schema: tool.output_schema }, "Output has the observed shape", "low"));

  // ---------------------------------------------------------------- invariants
  const inv: Clause[] = [
    clause("inv_no_unapproved_endpoint", "network", "no_unapproved_endpoint", {}, "No unapproved first-party endpoint is called", "high"),
    clause("inv_no_third_party", "network", "no_third_party", {}, "No third-party request is made", "high"),
    clause("inv_storage_untouched", "dom", "storage_untouched", {}, "No browser storage writes", "medium"),
  ];
  for (const mi of manifest.invariants ?? []) {
    if (route.tablesWritten.includes(mi.table)) inv.push(clause(mi.id, "db", mi.kind, { table: mi.table, where: mi.where }, mi.description, mi.severity));
  }
  const inserted = route.statements.find((s) => s.op === "INSERT")?.table;
  if (tool.risk_level === "payment" && inserted) inv.push(clause("inv_at_most_once", "db", "at_most_once", { table: inserted }, `At most one ${inserted} row per intent`, "high"));

  return {
    tool_id: tool.tool_id,
    preconditions: pre,
    postconditions: post,
    invariants: inv,
    derived_from: [
      { surface: "code", ref: `${route.file}:${route.line}` },
      { surface: "network", ref: `${route.method} ${route.path}` },
    ],
  };
}
