/**
 * DOM/ARIA + network surfaces of F3. Crawls a logged-in sandbox session: discovers pages by following
 * same-origin links, clicks every button on every page from a fresh reset (replaying earlier "create"
 * clicks first so pages like the cart have content), and records which API requests each click fires,
 * with request and response bodies. Unclicked GET endpoints are probed directly so their response shapes
 * are known too.
 */
import type { Request } from "playwright";
import { matchEndpoint } from "../contracts/match.js";
import { interactiveItems, type Item } from "../sandbox/aria.js";
import type { Session } from "../sandbox/session.js";
import type { DomInput, DomTrigger, NetworkSample, TriggerRequest } from "./candidates.js";

export interface CrawlResult {
  pages: string[];
  triggers: DomTrigger[];
  samples: NetworkSample[];
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const toPattern = (p: string) => p.replace(/\/\d+(?=\/|$)/g, "/:id");
const keyOf = (i: Item) => i.testid ?? `${i.role}:${i.name}`;
const selectorOf = (i: Item) => (i.testid ? `[data-testid=${i.testid}]` : `${i.role}[name="${i.name}"]`);
const isButton = (i: Item) => i.role === "button" && i.tag !== "input";
const isControl = (i: Item) => i.tag === "input" || i.tag === "select" || i.tag === "textarea";
const MAX_PAGES = 12;
const MAX_PASSES = 3;

function fillValue(i: Item): string | null {
  if (i.tag === "select") return null; // keep the default option
  if (i.inputType === "number") return String(i.min ?? 1);
  if (i.inputType === "email" || i.field === "email") return "crawl@example.com";
  if (i.inputType === "password") return null;
  return `crawl_${i.field ?? "text"}`;
}

const domInputs = (items: Item[]): DomInput[] =>
  items
    .filter((i) => isControl(i) && i.field)
    .map((i) => ({
      name: i.field as string,
      tag: i.tag,
      ...(i.inputType ? { type: i.inputType } : {}),
      ...(i.min !== undefined ? { min: i.min } : {}),
      ...(i.max !== undefined ? { max: i.max } : {}),
      ...(i.options ? { options: i.options } : {}),
    }));

export async function crawl(session: Session, opts: { settleMs?: number } = {}): Promise<CrawlResult> {
  const settle = opts.settleMs ?? 600;
  const manifest = session.manifest;
  const page = session.crawlerPage();
  const samples: NetworkSample[] = [];
  const pending = new Map<Request, TriggerRequest>();
  const inflight: Promise<void>[] = [];
  let capturing: TriggerRequest[] | null = null;

  page.on("request", (req) => {
    if (!["fetch", "xhr"].includes(req.resourceType())) return;
    const m = matchEndpoint(manifest, req.method(), req.url(), req.resourceType());
    if (m.third_party) return;
    let body: unknown;
    try {
      body = req.postDataJSON() as unknown;
    } catch {
      body = undefined;
    }
    const r: TriggerRequest = { method: req.method(), path: m.path, ...(m.pattern ? { pattern: m.pattern } : {}), ...(body === undefined || body === null ? {} : { body }) };
    capturing?.push(r);
    pending.set(req, r);
  });
  page.on("response", (res) => {
    const r = pending.get(res.request());
    if (!r) return;
    pending.delete(res.request());
    inflight.push(
      res
        .json()
        .catch(() => null)
        .then((response: unknown) => {
          samples.push({ method: r.method, path: r.path, ...(r.pattern ? { pattern: r.pattern } : {}), status: res.status(), ...(r.body === undefined ? {} : { request: r.body }), response });
        }),
    );
  });

  // ---------------------------------------------------------------- page discovery
  await session.reset();
  const pages = new Map<string, string>(); // pattern -> first concrete path
  const queue = [manifest.home_path ?? "/"];
  while (queue.length && pages.size < MAX_PAGES) {
    const p = queue.shift() as string;
    if (pages.has(toPattern(p))) continue;
    pages.set(toPattern(p), p);
    await session.domAction({ action: "navigate", url: p });
    for (const i of await interactiveItems(page)) {
      const href = i.href?.split("#")[0] ?? "";
      if (i.tag === "a" && href.startsWith("/") && !/^\/(logout|login)\b/.test(href)) queue.push(href);
    }
  }

  // ---------------------------------------------------------------- clicks
  const setup: { path: string; key: string }[] = [];
  const triggers = new Map<string, DomTrigger>();

  const fillAndClick = async (key: string): Promise<boolean> => {
    const items = await interactiveItems(page);
    for (const i of items.filter(isControl)) {
      const v = fillValue(i);
      if (v !== null) await session.domAction({ action: "type", ref: i.ref, text: v });
    }
    const target = (await interactiveItems(page)).find((i) => isButton(i) && keyOf(i) === key);
    if (!target) return false;
    await session.domAction({ action: "click", ref: target.ref });
    await sleep(settle);
    return true;
  };
  const prepare = async (path: string) => {
    await session.reset();
    for (const s of setup) {
      await session.domAction({ action: "navigate", url: s.path });
      await fillAndClick(s.key);
    }
    await session.domAction({ action: "navigate", url: path });
  };

  for (let pass = 0; pass < MAX_PASSES; pass++) {
    const before = triggers.size;
    for (const [pattern, path] of pages) {
      await prepare(path);
      const buttons = (await interactiveItems(page)).filter(isButton);
      const newSetup: { path: string; key: string }[] = [];
      for (const b of buttons) {
        const id = `${pattern}|${keyOf(b)}`;
        if (triggers.has(id)) continue;
        await prepare(path);
        const inputs = domInputs(await interactiveItems(page));
        capturing = [];
        const clicked = await fillAndClick(keyOf(b));
        const requests = capturing;
        capturing = null;
        if (!clicked) continue;
        triggers.set(id, { page: pattern, selector: selectorOf(b), role: b.role, name: b.name, ...(b.testid ? { testid: b.testid } : {}), inputs, requests });
        const createsState = requests.some((r) => r.method === "POST" && manifest.approved_endpoints.some((e) => e.method === "POST" && e.path === r.pattern && e.risk_level === "write"));
        if (createsState && !setup.some((s) => s.key === keyOf(b))) newSetup.push({ path, key: keyOf(b) });
      }
      setup.push(...newSetup);
    }
    if (triggers.size === before) break;
  }

  // ---------------------------------------------------------------- probe GET endpoints never seen
  await prepare(manifest.home_path ?? "/");
  for (const e of manifest.approved_endpoints.filter((x) => x.method === "GET")) {
    if (samples.some((s) => s.method === "GET" && s.pattern === e.path)) continue;
    await page.evaluate((url) => fetch(url).then((r) => r.text()), e.path.replace(/:\w+/g, "1"));
  }
  await sleep(200);
  await Promise.all(inflight);
  return { pages: [...pages.keys()], triggers: [...triggers.values()], samples };
}
