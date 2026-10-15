/**
 * Decides, for one observed request, whether it is first-party, approved by the app manifest, and which
 * endpoint pattern it hit. Shared by the sandbox observers and the checkers.
 */
import type { AppManifest, RiskLevel } from "./types.js";

export interface EndpointMatch {
  approved: boolean;
  third_party: boolean;
  host: string;
  path: string;
  pattern?: string;
  risk_level?: RiskLevel;
}

const API_RESOURCE_TYPES = new Set(["fetch", "xhr"]);

export function normalisePath(p: string): string {
  return p.length > 1 && p.endsWith("/") ? p.slice(0, -1) : p;
}

/** `/api/cart/:product_id` matches `/api/cart/3`; a `:param` segment never spans a `/`. */
export function patternMatches(pattern: string, path: string): boolean {
  const a = normalisePath(pattern).split("/");
  const b = normalisePath(path).split("/");
  return a.length === b.length && a.every((seg, i) => seg.startsWith(":") ? (b[i] ?? "") !== "" : seg === b[i]);
}

/**
 * @param resourceType Playwright resource type. First-party non-fetch/xhr GETs (page loads, assets) are
 *   approved; without a resource type every first-party request must match an approved endpoint.
 */
export function matchEndpoint(manifest: AppManifest, method: string, url: string, resourceType?: string): EndpointMatch {
  const u = new URL(url);
  const path = normalisePath(u.pathname);
  if (!manifest.approved_hosts.includes(u.host)) return { approved: false, third_party: true, host: u.host, path };
  const hit = manifest.approved_endpoints.find((e) => e.method === method.toUpperCase() && patternMatches(e.path, path));
  if (hit) return { approved: true, third_party: false, host: u.host, path, pattern: hit.path, ...(hit.risk_level ? { risk_level: hit.risk_level } : {}) };
  const pageLoad = resourceType !== undefined && !API_RESOURCE_TYPES.has(resourceType) && method.toUpperCase() === "GET";
  return { approved: pageLoad, third_party: false, host: u.host, path };
}
