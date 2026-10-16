/**
 * Fuses the code surface (routes), DOM/ARIA surface (UI triggers found by the crawler) and network surface
 * (observed requests/responses) into one candidate per approved API route. A candidate becomes one atomic
 * tool; UI triggers that fire several state-changing endpoints are not atomic and are not used as evidence.
 */
import { patternMatches } from "../contracts/match.js";
import type { AppManifest, ApprovedEndpoint, JsonSchema, RiskLevel } from "../contracts/types.js";
import type { RouteEvidence } from "./repo.js";

export interface DomInput {
  name: string;
  tag: string;
  type?: string;
  min?: number;
  max?: number;
  options?: string[];
}

export interface TriggerRequest {
  method: string;
  path: string;
  pattern?: string;
  body?: unknown;
}

export interface DomTrigger {
  /** Page pattern, e.g. /products/:id. */
  page: string;
  /** Concrete page the control was clicked on, e.g. /products/1. */
  pagePath?: string;
  selector: string;
  role: string;
  name: string;
  testid?: string;
  /** data-* attributes of the clicked control (row identity such as data-product-id). */
  data?: Record<string, string>;
  inputs: DomInput[];
  requests: TriggerRequest[];
  /** What the user saw after the click: page path and live status text. */
  after?: { url: string; status: string };
}

export interface NetworkSample {
  method: string;
  path: string;
  pattern?: string;
  status: number;
  request?: unknown;
  response: unknown;
}

export type InputType = "integer" | "number" | "string" | "boolean";

export interface InputField {
  name: string;
  type: InputType;
  required: boolean;
  source: "path" | "body";
  minimum?: number;
  maximum?: number;
  enum?: string[];
  const?: unknown;
}

export interface Candidate {
  app: string;
  route: RouteEvidence;
  endpoint: ApprovedEndpoint;
  risk_level: RiskLevel;
  triggers: DomTrigger[];
  samples: NetworkSample[];
  inputs: InputField[];
  outputSchema?: JsonSchema;
}

export interface Rejection {
  ref: string;
  reason: string;
}

const AUTH_ROUTES = new Set(["POST /api/login"]);
export const hits = (method: string, routePath: string, r: { method: string; path: string; pattern?: string }) =>
  r.method.toUpperCase() === method && (r.pattern ? r.pattern === routePath : patternMatches(routePath, r.path));

function inferType(values: unknown[]): InputType {
  if (values.length === 0) return "string";
  if (values.every((v) => typeof v === "boolean")) return "boolean";
  if (values.every((v) => Number.isInteger(v))) return "integer";
  if (values.every((v) => typeof v === "number")) return "number";
  return "string";
}

function valueSchema(v: unknown): JsonSchema {
  if (v === null) return { type: "null" };
  if (Array.isArray(v)) {
    const first = v[0];
    return first !== null && typeof first === "object" && !Array.isArray(first) ? { type: "array", items: { type: "object", properties: objectProps(first as Record<string, unknown>) } } : { type: "array" };
  }
  if (typeof v === "object") return { type: "object" };
  if (Number.isInteger(v)) return { type: "integer" };
  return { type: typeof v };
}

function objectProps(o: Record<string, unknown>): Record<string, JsonSchema> {
  return Object.fromEntries(Object.entries(o).map(([k, v]) => [k, valueSchema(v)]));
}

export function outputSchemaOf(response: unknown): JsonSchema | undefined {
  if (Array.isArray(response)) {
    const first = response[0];
    const items = first !== null && typeof first === "object" && !Array.isArray(first) ? { type: "object", properties: objectProps(first as Record<string, unknown>) } : {};
    return { type: "object", required: ["items"], properties: { items: { type: "array", items } } };
  }
  if (response !== null && typeof response === "object") {
    const o = response as Record<string, unknown>;
    return { type: "object", required: Object.keys(o), properties: objectProps(o) };
  }
  return undefined;
}

const stateChanging = (t: DomTrigger) => new Set(t.requests.filter((r) => r.method.toUpperCase() !== "GET").map((r) => `${r.method.toUpperCase()} ${r.pattern ?? r.path}`));

export function buildCandidates(routes: RouteEvidence[], triggers: DomTrigger[], samples: NetworkSample[], manifest: AppManifest): { candidates: Candidate[]; rejected: Rejection[] } {
  const rejected: Rejection[] = [];
  const atomic = triggers.filter((t) => {
    const n = stateChanging(t).size;
    if (n > 1) rejected.push({ ref: t.selector, reason: `trigger fires ${n} state-changing endpoints; not atomic` });
    return n <= 1;
  });

  const candidates: Candidate[] = [];
  for (const route of routes) {
    const key = `${route.method} ${route.path}`;
    if (!route.path.startsWith("/api/") || AUTH_ROUTES.has(key)) continue;
    const endpoint = manifest.approved_endpoints.find((e) => e.method === route.method && e.path === route.path);
    if (!endpoint) {
      rejected.push({ ref: key, reason: "route is not an approved endpoint in the app manifest" });
      continue;
    }
    const routeTriggers = atomic.filter((t) => t.requests.some((r) => hits(route.method, route.path, r)));
    const routeSamples = samples.filter((s) => hits(route.method, route.path, s));
    const bodies = [...routeSamples.map((s) => s.request), ...routeTriggers.flatMap((t) => t.requests.filter((r) => hits(route.method, route.path, r)).map((r) => r.body))].filter(
      (b): b is Record<string, unknown> => b !== null && typeof b === "object",
    );
    const domInputs = routeTriggers.flatMap((t) => t.inputs);

    const inputs: InputField[] = route.pathParams.map((name) => ({ name, type: name === "id" || name.endsWith("_id") ? "integer" : "string", required: true, source: "path" }));
    for (const name of route.bodyFields) {
      const values = bodies.filter((b) => name in b).map((b) => b[name]);
      const field: InputField = { name, type: inferType(values), required: true, source: "body" };
      const dom = domInputs.find((d) => d.name === name);
      if (dom?.min !== undefined) field.minimum = dom.min;
      if (dom?.max !== undefined) field.maximum = dom.max;
      if (dom?.options?.length) field.enum = dom.options;
      if (!dom && field.type === "boolean" && values.length > 0 && values.every((v) => v === values[0])) field.const = values[0];
      inputs.push(field);
    }

    // The most informative 2xx response (e.g. a filled cart rather than an empty one) defines the shape.
    const ok = routeSamples
      .filter((s) => s.status >= 200 && s.status < 300 && s.response !== null && s.response !== undefined)
      .sort((a, b) => JSON.stringify(b.response).length - JSON.stringify(a.response).length)[0];
    const outputSchema = ok ? outputSchemaOf(ok.response) : undefined;
    candidates.push({
      app: manifest.app,
      route,
      endpoint,
      risk_level: endpoint.risk_level ?? (route.method === "GET" ? "read" : route.method === "DELETE" ? "delete" : "write"),
      triggers: routeTriggers,
      samples: routeSamples,
      inputs,
      ...(outputSchema ? { outputSchema } : {}),
    });
  }
  return { candidates, rejected };
}
