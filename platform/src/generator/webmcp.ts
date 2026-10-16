/**
 * WebMCP-native tool set. State-changing actions become `ui` tools that act through the page itself:
 * they fill the page's own form controls and click its own button, so the app's code runs, the page
 * updates in front of the user, and the tool returns the response that click produced. Each is scoped to
 * the page its control lives on; context such as "the product shown" comes from the page, not from
 * arguments. Reads stay `api` tools available on every page. Write routes no UI control performs are
 * skipped: a WebMCP tool can only do what the page lets the user do.
 */
import { deriveContract } from "../contracts/derive.js";
import type { AppManifest, Clause, ToolContract, ToolDefinition } from "../contracts/types.js";
import { hits, type Candidate, type DomTrigger, type InputField, type Rejection } from "./candidates.js";
import { emitTool, provenance, type Namer } from "./emit.js";

type Role = { field: InputField; how: "fill" } | { field: InputField; how: "row"; attr: string };

const toPattern = (p: string) => p.replace(/\/\d+(?=\/|$)/g, "/:id");
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pathRegex = (pattern: string) => `^${pattern.split("/").map((seg) => (seg.startsWith(":") ? "[^/]+" : escapeRe(seg))).join("/")}$`;
const sentence = (name: string) => name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, " ");

function params(pattern: string, concrete: string): Record<string, string> {
  const a = pattern.split("/");
  const b = concrete.split("/");
  return Object.fromEntries(a.flatMap((seg, i) => (seg.startsWith(":") && b[i] !== undefined ? [[seg.slice(1), b[i] as string]] : [])));
}

/** Decides, for every parameter the endpoint receives, whether the agent supplies it and how. */
function classify(c: Candidate, t: DomTrigger): Role[] {
  const req = t.requests.find((r) => hits(c.route.method, c.route.path, r));
  const observed: Record<string, unknown> = { ...(req ? params(c.route.path, req.path) : {}), ...((req?.body ?? {}) as Record<string, unknown>) };
  const pageValues = new Set(Object.values(params(t.page, t.pagePath ?? t.page)));
  const roles: Role[] = [];
  for (const field of c.inputs) {
    if (t.inputs.some((i) => i.name === field.name)) {
      roles.push({ field, how: "fill" });
      continue;
    }
    const value = observed[field.name];
    const attr = Object.entries(t.data ?? {}).find(([, v]) => v === String(value))?.[0];
    if (attr && !pageValues.has(String(value))) roles.push({ field, how: "row", attr });
    // Otherwise the page supplies it (shown entity, constant flag such as confirm=true): not an argument.
  }
  return roles;
}

function uiHandlerCode(c: Candidate, t: DomTrigger, roles: Role[]): string {
  const row = roles.find((r) => r.how === "row") as Extract<Role, { how: "row" }> | undefined;
  const target = row ? `${JSON.stringify(t.selector)} + '[${row.attr}="' + CSS.escape(String(input.${row.field.name})) + '"]'` : JSON.stringify(t.selector);
  const fills = roles
    .filter((r) => r.how === "fill")
    .map((r) => `  if (input.${r.field.name} !== undefined) fill(${JSON.stringify(r.field.name)}, input.${r.field.name});`)
    .join("\n");
  const label = JSON.stringify(t.name);
  return `async (input) => {
  const target = document.querySelector(${target});
  if (!target) throw new Error(${label} + " is not available on this page${row ? ` for ${row.field.name}=" + input.${row.field.name} + "` : ""}");
  const fill = (name, value) => {
    const el = document.querySelector('[name="' + name + '"]');
    if (!el) throw new Error("form field " + name + " is not on this page");
    const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, String(value));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
${fills}
  // Capture the response of the request this click makes, reading it before the page can move on.
  const original = window.fetch;
  const response = new Promise((resolve, reject) => {
    const timer = setTimeout(() => { window.fetch = original; reject(new Error(${label} + " did not reach the server within 10 s")); }, 10000);
    window.fetch = async (resource, init) => {
      const res = await original(resource, init);
      const url = new URL(typeof resource === "string" ? resource : resource.url, location.href);
      const method = String((init && init.method) || (resource && resource.method) || "GET").toUpperCase();
      if (method === ${JSON.stringify(c.route.method)} && new RegExp(${JSON.stringify(pathRegex(c.route.path))}).test(url.pathname)) {
        window.fetch = original;
        clearTimeout(timer);
        resolve({ status: res.status, text: await res.clone().text() });
      }
      return res;
    };
  });
  target.click();
  const { status, text } = await response;
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
  if (status >= 400) throw new Error(${label} + " failed: " + status + " " + String(text).slice(0, 200));
  return Array.isArray(data) ? { items: data } : data;
}`;
}

function uiContract(base: ToolContract, roles: Role[], t: DomTrigger): ToolContract {
  const inputs = new Set(roles.map((r) => r.field.name));
  const usesOnlyInputs = (cl: Clause) => Object.values((cl.params.where ?? {}) as Record<string, unknown>).every((v) => typeof v !== "string" || !v.startsWith("$args.") || inputs.has(v.slice(6)));
  const clause = (id: string, kind: Clause["kind"], p: Record<string, unknown>, description: string): Clause => ({ clause_id: id, surface: "dom", kind, params: p, description, severity: "medium" });
  const [auth, ...rest] = base.preconditions;
  const pre = [...(auth ? [auth] : []), clause("pre_control_present", "dom_exists", { selector: t.selector }, `"${t.name}" is on the page`), ...rest.filter(usesOnlyInputs)];
  const post = [...base.postconditions];
  const after = t.after;
  if (after && toPattern(after.url) !== toPattern(t.pagePath ?? t.page)) {
    const pattern = `^https?://[^/]+${toPattern(after.url).split("/").map((s) => (s.startsWith(":") ? "\\d+" : escapeRe(s))).join("/")}(?:[?#].*)?$`;
    post.push(clause("post_ui_url", "url_matches", { pattern }, `The page moves to ${toPattern(after.url)}`));
  } else if (after?.status) {
    post.push(clause("post_ui_status", "dom_text_contains", { selector: "[role=status]", text: after.status }, `The page tells the user "${after.status}"`));
  }
  return { ...base, preconditions: pre, postconditions: post };
}

export interface WebmcpBuild {
  tools: ToolDefinition[];
  contracts: ToolContract[];
  skipped: Rejection[];
}

export async function buildWebmcpTools(candidates: Candidate[], manifest: AppManifest, namer: Namer): Promise<WebmcpBuild> {
  const out: WebmcpBuild = { tools: [], contracts: [], skipped: [] };
  for (const c of candidates) {
    if (c.route.method === "GET") {
      const base = await emitTool(c, manifest, namer);
      const tool = { ...base, handler: { ...base.handler, page: "*" } };
      out.tools.push(tool);
      out.contracts.push(deriveContract(tool, c.route, manifest));
      continue;
    }
    const t = c.triggers[0];
    if (!t) {
      out.skipped.push({ ref: `${c.route.method} ${c.route.path}`, reason: "no control on any page performs this action; a WebMCP tool can only do what the page lets the user do" });
      continue;
    }
    const roles = classify(c, t);
    const naming = await namer(c);
    const row = roles.find((r) => r.how === "row");
    const fillNames = roles.filter((r) => r.how === "fill").map((r) => r.field.name);
    const notes = [
      `${sentence(naming.name)}. Use it on the ${t.page} page: it ${fillNames.length ? `fills ${fillNames.join(", ")} and ` : ""}clicks "${t.name}", so the page itself performs the action and shows the result.`,
      Object.keys(params(t.page, t.pagePath ?? t.page)).length ? "It acts on the item shown on that page." : "",
      row ? `Pass ${row.field.name} to choose which row's "${t.name}" button to click.` : "",
      c.risk_level === "payment" ? "This spends money; the page asks the user to confirm first." : c.risk_level === "delete" ? "This removes data; the page asks the user to confirm first." : "",
    ].filter(Boolean);
    const properties = Object.fromEntries(
      roles.map(({ field }) => {
        const p: Record<string, unknown> = { type: field.type, description: naming.paramDescriptions[field.name] ?? field.name };
        if (field.minimum !== undefined) p.minimum = field.minimum;
        if (field.maximum !== undefined) p.maximum = field.maximum;
        if (field.enum) p.enum = field.enum;
        return [field.name, p];
      }),
    );
    const tool: ToolDefinition = {
      tool_id: `${manifest.app}.${naming.name}`,
      app: manifest.app,
      name: naming.name,
      description: notes.join(" "),
      input_schema: { type: "object", properties, required: Object.keys(properties), additionalProperties: false },
      ...(c.outputSchema ? { output_schema: c.outputSchema } : {}),
      handler: {
        kind: "ui",
        code: uiHandlerCode(c, t, roles),
        http: { method: c.route.method as "POST" | "PUT" | "PATCH" | "DELETE", path_template: c.route.path.replace(/:(\w+)/g, "{$1}") },
        selectors: [t.selector],
        page: t.page,
        ...(t.pagePath ? { page_example: t.pagePath } : {}),
      },
      risk_level: c.risk_level,
      atomic: true,
      provenance: provenance(c),
      version: 1,
      metadata_revision: 0,
      status: "generated",
    };
    out.tools.push(tool);
    out.contracts.push(uiContract(deriveContract(tool, c.route, manifest), roles, t));
  }
  return out;
}
