/**
 * Typed workflow graph for one app (contracts/workflow_graph.schema.json). Nodes are tools with type
 * signatures, state they read/write and observed violation rates. Edges come from four sources:
 *   order  — consecutive calls seen in verdict traces           (evidence "trace")
 *   state  — a tool creates rows another tool's precondition needs (evidence "contract")
 *   data   — an id one tool returned was later passed to another (evidence "trace", value flow)
 *   data   — an output field name equals another tool's input name (evidence "rule", label unknown)
 * Value flow recovers dependencies name matching misses (get_product.id → add_to_cart.product_id);
 * S2 learns to predict those from the rest of the graph.
 */
import type { GraphEdge, GraphInvariant, GraphNode, JsonSchema, ToolContract, ToolDefinition, Verdict, WorkflowGraph } from "../contracts/types.js";

const isIdField = (name: string) => name === "id" || name.endsWith("_id");
const last = (path: string) => path.split(".").at(-1) ?? path;

/** Field paths of an output JSON Schema; arrays of objects contribute `<field>.<item field>`. */
export function schemaFields(schema: JsonSchema | undefined, prefix = ""): string[] {
  const props = (schema?.properties ?? {}) as Record<string, JsonSchema>;
  return Object.entries(props).flatMap(([k, v]) => {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v.type === "array" && (v.items as JsonSchema | undefined)?.properties) return schemaFields(v.items as JsonSchema, p);
    if (v.type === "object" && v.properties) return schemaFields(v, p);
    return [p];
  });
}

/** Primitive leaves of a value as [path, value]; array elements share their parent's path. */
function leaves(value: unknown, prefix = ""): [string, unknown][] {
  if (Array.isArray(value)) return value.slice(0, 50).flatMap((v) => leaves(v, prefix));
  if (value !== null && typeof value === "object") return Object.entries(value).flatMap(([k, v]) => leaves(v, prefix ? `${prefix}.${k}` : k));
  return prefix ? [[prefix, value]] : [];
}

/** Resource a tool acts on, from its name: shop.get_product -> product, shop.list_users -> user. */
const resourceOf = (toolId: string) => (toolId.split(".").at(-1) ?? "").split("_").slice(1).join("_").replace(/s$/, "");

/**
 * Whether an id that `src` returned at `leafPath` can plausibly be the `param` of `dst`: same field name
 * (view_cart items.product_id -> product_id), a bare `id` of the matching resource (get_product id ->
 * product_id), or a resource id into a tool acting on that resource (create_user id -> update_user id).
 */
export function idCompatible(src: string, leafPath: string, dst: string, param: string): boolean {
  const leaf = last(leafPath);
  if (leaf === param) return leaf !== "id" || resourceOf(src) === resourceOf(dst);
  const srcRes = resourceOf(src);
  if (leaf === "id" && param.endsWith("_id")) return srcRes !== "" && srcRes.includes(param.slice(0, -3));
  if (param === "id" && leaf.endsWith("_id")) return resourceOf(dst).includes(leaf.slice(0, -3));
  return false;
}

const runOrder = (a: Verdict, b: Verdict) => a.started_at.localeCompare(b.started_at) || Number(/\d+$/.exec(a.run_id)?.[0] ?? 0) - Number(/\d+$/.exec(b.run_id)?.[0] ?? 0);

export function valueFlowEdges(verdicts: Verdict[]): GraphEdge[] {
  const found = new Map<string, GraphEdge>();
  const bySession = new Map<string, Verdict[]>();
  for (const v of verdicts) bySession.set(v.session_id, [...(bySession.get(v.session_id) ?? []), v]);
  for (const runs of bySession.values()) {
    let epoch: { tool: string; path: string; value: string }[] = [];
    for (const d of [...runs].sort(runOrder)) {
      if (d.mode !== "concurrent" && (d.sequence_prefix ?? []).length === 0) epoch = [];
      for (const [field, value] of Object.entries(d.args)) {
        if (!isIdField(field) || value === null || value === undefined || typeof value === "boolean" || value === "") continue;
        for (const src of epoch.filter((o) => o.tool !== d.tool_id && o.value === String(value) && idCompatible(o.tool, o.path, d.tool_id, field))) {
          const key = `${src.tool}|${d.tool_id}|${field}`;
          found.set(key, { src: src.tool, dst: d.tool_id, type: "data", field, evidence: "trace", confidence: 1, label: true });
        }
      }
      for (const [path, value] of leaves(d.output)) if (isIdField(last(path)) && value !== null && typeof value !== "boolean") epoch.push({ tool: d.tool_id, path, value: String(value) });
    }
  }
  return [...found.values()];
}

export function nameMatchEdges(tools: ToolDefinition[]): GraphEdge[] {
  const edges: GraphEdge[] = [];
  for (const src of tools) {
    const outs = new Set(schemaFields(src.output_schema).map(last));
    for (const dst of tools) {
      if (dst.tool_id === src.tool_id) continue;
      for (const input of Object.keys((dst.input_schema.properties ?? {}) as object)) {
        if (outs.has(input)) edges.push({ src: src.tool_id, dst: dst.tool_id, type: "data", field: input, evidence: "rule", confidence: 0.5, label: null });
      }
    }
  }
  return edges;
}

const insertsInto = (c: ToolContract) =>
  c.postconditions
    .filter((p) => p.kind === "db_delta" && p.clause_id.startsWith("post_db_"))
    .filter((p) => {
      const ins = p.params.inserted;
      return typeof ins === "number" ? ins >= 1 : ins !== null && typeof ins === "object" && ((ins as { min?: number }).min ?? 0) >= 1;
    })
    .map((p) => String(p.params.table));
const requiresRows = (c: ToolContract) => [...new Set(c.preconditions.filter((p) => p.kind === "db_row_exists").map((p) => String(p.params.table)))];

export function stateEdges(contracts: ToolContract[]): GraphEdge[] {
  const edges: GraphEdge[] = [];
  for (const src of contracts)
    for (const table of insertsInto(src))
      for (const dst of contracts) {
        if (dst.tool_id !== src.tool_id && requiresRows(dst).includes(table)) edges.push({ src: src.tool_id, dst: dst.tool_id, type: "state", field: table, evidence: "contract", confidence: 0.9, label: true });
      }
  return edges;
}

export function orderEdges(verdicts: Verdict[]): GraphEdge[] {
  const pairs = new Map<string, number>();
  const outgoing = new Map<string, number>();
  for (const v of verdicts) {
    const prev = v.sequence_prefix?.at(-1);
    if (!prev) continue;
    const key = `${prev}|${v.tool_id}`;
    pairs.set(key, (pairs.get(key) ?? 0) + 1);
    outgoing.set(prev, (outgoing.get(prev) ?? 0) + 1);
  }
  return [...pairs].map(([key, n]) => {
    const [src, dst] = key.split("|") as [string, string];
    return { src, dst, type: "order" as const, evidence: "trace" as const, confidence: Math.round((n / (outgoing.get(src) ?? n)) * 1000) / 1000, label: true };
  });
}

const PRIORITY: Record<string, number> = { trace: 3, contract: 2, manual: 2, gnn: 1, rule: 0 };

function mergeEdges(edges: GraphEdge[]): GraphEdge[] {
  const out = new Map<string, GraphEdge>();
  for (const e of edges) {
    const key = `${e.src}|${e.dst}|${e.type}|${e.field ?? ""}`;
    const prev = out.get(key);
    if (!prev) {
      out.set(key, e);
      continue;
    }
    const better = (PRIORITY[e.evidence] ?? 0) > (PRIORITY[prev.evidence] ?? 0) ? e : prev;
    out.set(key, { ...better, confidence: Math.max(prev.confidence, e.confidence), label: prev.label === true || e.label === true ? true : (better.label ?? null) });
  }
  return [...out.values()];
}

export function buildGraph(app: string, tools: ToolDefinition[], contracts: ToolContract[], verdicts: Verdict[]): WorkflowGraph {
  const contractOf = new Map(contracts.map((c) => [c.tool_id, c]));
  const nodes: GraphNode[] = tools.map((t) => {
    const c = contractOf.get(t.tool_id);
    const runs = verdicts.filter((v) => v.tool_id === t.tool_id);
    const bad = runs.filter((v) => v.violations.some((x) => x.category !== "precondition")).length;
    return {
      id: t.tool_id,
      risk_level: t.risk_level,
      input_fields: Object.keys((t.input_schema.properties ?? {}) as object),
      output_fields: schemaFields(t.output_schema),
      state_reads: c ? requiresRows(c) : [],
      state_writes: c ? [...new Set(c.postconditions.filter((p) => p.clause_id.startsWith("post_db_")).map((p) => String(p.params.table)))] : [],
      ...(t.status ? { status: t.status } : {}),
      violation_rate: runs.length ? Math.round((bad / runs.length) * 1000) / 1000 : 0,
    };
  });
  const state = stateEdges(contracts);
  const edges = mergeEdges([...valueFlowEdges(verdicts), ...state, ...orderEdges(verdicts), ...nameMatchEdges(tools)]);
  const slug = (s: string) => s.replace(/\./g, "_");
  const invariants: GraphInvariant[] = state.map((e) => ({
    id: `inv_requires_${slug(e.dst)}_${slug(e.src)}`,
    kind: "requires",
    tools: [e.src, e.dst],
    description: `${e.dst} needs ${e.field} rows that ${e.src} creates`,
  }));
  for (const c of contracts.filter((k) => k.invariants.some((i) => i.kind === "at_most_once"))) {
    invariants.push({ id: `inv_at_most_once_${slug(c.tool_id)}`, kind: "at_most_once", tools: [c.tool_id], description: `${c.tool_id} must take effect at most once per intent` });
    invariants.push({ id: `inv_never_concurrent_${slug(c.tool_id)}`, kind: "never_concurrent", tools: [c.tool_id], description: `${c.tool_id} must not run concurrently with itself` });
  }
  return { app, version: Math.max(1, ...tools.map((t) => t.version)), generated_at: new Date().toISOString(), nodes, edges, invariants };
}
