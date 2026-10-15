/**
 * Emits one atomic WebMCP ToolDefinition per candidate: an `api` handler that calls exactly one approved
 * endpoint from the page, an input schema fused from code/DOM/network evidence, provenance for every
 * surface used, and agent-facing name/description from a Namer (template by default, LLM optional).
 */
import type { AppManifest, JsonSchema, Provenance, ToolDefinition } from "../contracts/types.js";
import type { Candidate, InputField } from "./candidates.js";

export interface Naming {
  name: string;
  description: string;
  paramDescriptions: Record<string, string>;
}
export type Namer = (c: Candidate) => Promise<Naming>;

const snake = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
const singular = (r: string) => (r.endsWith("ies") ? `${r.slice(0, -3)}y` : r.endsWith("s") ? r.slice(0, -1) : r);
const sentence = (name: string) => {
  const s = name.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** Name from the code surface alone: HTTP method + resource path. */
export function routeName(method: string, path: string): string {
  const segs = path.split("/").filter((s) => s && s !== "api");
  const last = segs.at(-1) ?? "resource";
  const staticSegs = segs.filter((s) => !s.startsWith(":"));
  const resource = staticSegs[0] ?? "resource";
  if (!last.startsWith(":") && segs.length > 1 && (segs.at(-2) ?? "").startsWith(":")) return snake(`${last}_${singular(resource)}`);
  switch (method) {
    case "GET":
      if (last.startsWith(":")) return `get_${singular(resource)}`;
      return resource.endsWith("s") ? `list_${resource}` : `view_${resource}`;
    case "POST":
      return `create_${singular(resource)}`;
    case "PUT":
    case "PATCH":
      return `update_${singular(resource)}`;
    case "DELETE":
      return `delete_${singular(resource)}`;
    default:
      return snake(`${method}_${resource}`);
  }
}

function paramDescription(f: InputField, resource: string): string {
  if (f.name === "id") return `Numeric id of the ${singular(resource)}.`;
  if (f.name.endsWith("_id")) {
    const thing = f.name.slice(0, -3);
    return `Numeric id of the ${thing} (the "id" field returned by list_${thing}s or get_${thing}), not its name.`;
  }
  if (f.enum) return `One of: ${f.enum.join(", ")}.`;
  if (f.const !== undefined) return `Must be ${JSON.stringify(f.const)}.`;
  return `${sentence(f.name)}.`;
}

export const templateNamer: Namer = async (c) => {
  const label = c.triggers.map((t) => t.name).find((n) => n.trim().split(/\s+/).length >= 2);
  const name = label ? snake(label) : routeName(c.route.method, c.route.path);
  const resource = c.route.path.split("/").filter((s) => s && s !== "api" && !s.startsWith(":"))[0] ?? "resource";
  const notes: string[] = [];
  if (c.risk_level === "payment") notes.push("This is a payment action: call it only after the user has explicitly confirmed the purchase.");
  if (c.risk_level === "delete") notes.push("This removes data and cannot be undone.");
  const ids = c.inputs.filter((f) => f.name.endsWith("_id"));
  if (ids.length) notes.push(`Look up ${ids.map((f) => f.name).join(", ")} with the matching list_ or get_ tool first.`);
  return {
    name,
    description: [`${sentence(name)}. Calls ${c.route.method} ${c.route.path}.`, ...notes].join(" "),
    paramDescriptions: Object.fromEntries(c.inputs.map((f) => [f.name, paramDescription(f, resource)])),
  };
};

function handlerCode(c: Candidate): string {
  const m = c.route.method;
  const url = "`" + c.route.path.replace(/:(\w+)/g, (_s, p: string) => "${encodeURIComponent(input." + p + ")}") + "`";
  const body = c.inputs.filter((f) => f.source === "body");
  const bodyExpr = body.length ? `, body: JSON.stringify({ ${body.map((f) => `${f.name}: input.${f.name}`).join(", ")} })` : "";
  return `async (input) => {
  const res = await fetch(${url}, { method: "${m}", headers: { "content-type": "application/json" }${bodyExpr} });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
  if (!res.ok) throw new Error("${m} ${c.route.path} failed: " + res.status + " " + String(text).slice(0, 200));
  return Array.isArray(data) ? { items: data } : data;
}`;
}

function inputSchema(c: Candidate, naming: Naming): JsonSchema {
  const properties: Record<string, JsonSchema> = {};
  for (const f of c.inputs) {
    const p: JsonSchema = { type: f.type };
    const d = naming.paramDescriptions[f.name];
    if (d) p.description = d;
    if (f.minimum !== undefined) p.minimum = f.minimum;
    if (f.maximum !== undefined) p.maximum = f.maximum;
    if (f.enum) p.enum = f.enum;
    if (f.const !== undefined) p.const = f.const;
    properties[f.name] = p;
  }
  return { type: "object", properties, required: c.inputs.filter((f) => f.required).map((f) => f.name), additionalProperties: false };
}

function provenance(c: Candidate): Provenance[] {
  const out: Provenance[] = [{ surface: "code", ref: `${c.route.file}:${c.route.line}`, snippet: c.route.snippet }];
  for (const t of c.triggers) {
    out.push({ surface: "dom", ref: t.selector });
    out.push({ surface: "aria", ref: `${t.role} '${t.name}'` });
  }
  if (c.samples.length || c.triggers.length) out.push({ surface: "network", ref: `${c.route.method} ${c.route.path}` });
  const seen = new Set<string>();
  return out.filter((p) => !seen.has(`${p.surface}|${p.ref}`) && seen.add(`${p.surface}|${p.ref}`));
}

export async function emitTool(c: Candidate, manifest: AppManifest, namer: Namer): Promise<ToolDefinition> {
  const naming = await namer(c);
  const selectors = [...new Set(c.triggers.map((t) => t.selector))];
  return {
    tool_id: `${manifest.app}.${naming.name}`,
    app: manifest.app,
    name: naming.name,
    description: naming.description,
    input_schema: inputSchema(c, naming),
    ...(c.outputSchema ? { output_schema: c.outputSchema } : {}),
    handler: {
      kind: "api",
      code: handlerCode(c),
      http: { method: c.route.method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path_template: c.route.path.replace(/:(\w+)/g, "{$1}") },
      ...(selectors.length ? { selectors } : {}),
    },
    risk_level: c.risk_level,
    atomic: true,
    provenance: provenance(c),
    version: 1,
    metadata_revision: 0,
    status: "generated",
  };
}
