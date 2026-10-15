/**
 * Browser-side observation for one sandbox session: network requests/responses (Playwright events),
 * third-party blocking (context.route abort), DOM mutations and storage writes (init script reporting
 * through an exposed binding), console messages and navigations. Everything is forwarded to `emit` with
 * the page it came from, so concurrent calls running in separate pages can be attributed per call.
 */
import type { BrowserContext, Page, Request } from "playwright";
import { matchEndpoint } from "../contracts/match.js";
import type { AppManifest, EventKind } from "../contracts/types.js";

export type Emit = (page: Page | null, kind: EventKind, data: Record<string, unknown>) => void;

const INIT_SCRIPT = `(() => {
  if (window.__specxInstalled) return;
  window.__specxInstalled = true;
  const emit = (kind, data) => { try { window.__specx_emit({ kind, data }); } catch (_) {} };
  const sel = (n) => {
    if (n && n.nodeType !== 1) n = n.parentElement;
    if (!n) return "";
    if (n.dataset && n.dataset.testid) return "[data-testid=" + n.dataset.testid + "]";
    if (n.id) return "#" + n.id;
    return n.tagName.toLowerCase();
  };
  let pending = null;
  const flush = () => { if (pending) { emit("dom_mutation", pending); pending = null; } };
  const observer = new MutationObserver((muts) => {
    for (const m of muts) {
      if (!pending) { pending = { added: 0, removed: 0, attr_changed: 0, text_changed: 0, target_selector: sel(m.target) }; setTimeout(flush, 30); }
      if (m.type === "childList") { pending.added += m.addedNodes.length; pending.removed += m.removedNodes.length; }
      else if (m.type === "attributes") pending.attr_changed++;
      else pending.text_changed++;
    }
  });
  const start = () => observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  if (document.documentElement) start(); else document.addEventListener("DOMContentLoaded", start);
  try {
    const P = Storage.prototype;
    const area = (s) => (s === window.localStorage ? "local" : "session");
    const set = P.setItem, rem = P.removeItem, clr = P.clear;
    P.setItem = function (k, v) { emit("storage", { area: area(this), op: "set", key: String(k) }); return set.call(this, k, v); };
    P.removeItem = function (k) { emit("storage", { area: area(this), op: "remove", key: String(k) }); return rem.call(this, k); };
    P.clear = function () { emit("storage", { area: area(this), op: "clear", key: "*" }); return clr.call(this); };
    const desc = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(Document.prototype, "cookie", {
      configurable: true,
      get() { return desc.get.call(this); },
      set(v) { emit("storage", { area: "cookie", op: "set", key: String(v).split("=")[0].trim() }); desc.set.call(this, v); },
    });
  } catch (_) { /* about:blank and other opaque origins have no storage */ }
})();`;

let requestCounter = 0;
const requestIds = new WeakMap<Request, string>();
const idOf = (r: Request): string => {
  let id = requestIds.get(r);
  if (!id) {
    id = `q${++requestCounter}`;
    requestIds.set(r, id);
  }
  return id;
};

export async function observeContext(context: BrowserContext, manifest: AppManifest, emit: Emit): Promise<void> {
  await context.exposeBinding("__specx_emit", (source, evt: { kind: EventKind; data: Record<string, unknown> }) => emit(source.page, evt.kind, evt.data));
  await context.addInitScript({ content: INIT_SCRIPT });
  await context.route(
    (url) => /^https?:$/.test(url.protocol) && !manifest.approved_hosts.includes(url.host),
    (route) => route.abort("blockedbyclient"),
  );
}

export function observePage(page: Page, manifest: AppManifest, emit: Emit): void {
  page.on("request", (req) => {
    const m = matchEndpoint(manifest, req.method(), req.url(), req.resourceType());
    emit(page, "network_request", {
      request_id: idOf(req),
      method: req.method(),
      url: req.url(),
      host: m.host,
      path: m.path,
      third_party: m.third_party,
      approved: m.approved,
      body_bytes: req.postDataBuffer()?.length ?? 0,
      initiator: req.resourceType(),
    });
  });
  page.on("response", (res) => {
    emit(page, "network_response", {
      request_id: idOf(res.request()),
      status: res.status(),
      body_bytes: Number(res.headers()["content-length"] ?? 0),
      mime: res.headers()["content-type"] ?? "",
    });
  });
  page.on("console", (msg) => emit(page, "console", { level: msg.type(), text: msg.text().slice(0, 500) }));
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) emit(page, "navigation", { url: frame.url() });
  });
}
