/**
 * Sandbox HTTP API v1 (contracts/sandbox_api.md) — the only runtime boundary between the TypeScript
 * platform and the Python side. Bodies are validated with zod; errors use `{error: {code, message}}`;
 * every response carries header `x-specx-api-version: 1`.
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import express, { type NextFunction, type Request, type Response } from "express";
import { chromium, type Browser } from "playwright";
import { z, ZodError } from "zod";
import type { AppManifest, ToolContract, ToolDefinition } from "../contracts/types.js";
import { validate } from "../contracts/validate.js";
import { log } from "../log.js";
import { SEED_APPS_DIR } from "../paths.js";
import { SandboxError } from "./errors.js";
import { Session, type DomAction } from "./session.js";

const SOURCES = ["f1", "s1", "s1_random", "s1_coverage", "s6_approved", "s6_inject", "f2", "f4", "fixture"] as const;
const args = z.record(z.unknown());
const Body = {
  createSession: z.object({ app: z.string(), seed: z.number().int().optional(), leak: z.object({ kind: z.string(), delay_ms: z.number().int().min(0) }).optional() }),
  reset: z.object({ seed: z.number().int().optional() }),
  tools: z.object({ tools: z.array(z.unknown()), contracts: z.array(z.unknown()) }),
  invoke: z.object({
    tool_id: z.string(),
    args,
    source: z.enum(SOURCES),
    post_observe_ms: z.number().int().min(0).max(10_000).optional(),
    screenshot: z.boolean().optional(),
  }),
  concurrent: z.object({
    calls: z.array(z.object({ tool_id: z.string(), args })).min(1).max(8),
    source: z.enum(SOURCES),
    post_observe_ms: z.number().int().min(0).max(10_000).optional(),
  }),
  replay: z.object({ run_id: z.string() }),
  domAction: z.discriminatedUnion("action", [
    z.object({ action: z.literal("click"), ref: z.string() }),
    z.object({ action: z.literal("type"), ref: z.string(), text: z.string() }),
    z.object({ action: z.literal("press"), key: z.string() }),
    z.object({ action: z.literal("navigate"), url: z.string() }),
  ]),
  apply: z.object({ state: z.record(z.unknown()) }),
  leak: z.object({ kind: z.string(), delay_ms: z.number().int().min(0) }),
};

export interface Sandbox {
  app: express.Express;
  close: () => Promise<void>;
}

export function createSandbox(opts: { manifests: AppManifest[] }): Sandbox {
  const manifests = new Map(opts.manifests.map((m) => [m.app, validate<AppManifest>("app_manifest", m)]));
  const sessions = new Map<string, Session>();
  let browser: Promise<Browser> | null = null;
  const getBrowser = () => (browser ??= chromium.launch({ headless: true }));
  const app = express();
  app.disable("x-powered-by");
  app.use(express.json({ limit: "5mb" }));
  app.use((_req, res, next) => {
    res.setHeader("x-specx-api-version", "1");
    next();
  });

  const session = (req: Request): Session => {
    const s = sessions.get(String(req.params.id));
    if (!s) throw new SandboxError(404, "unknown_session", `session ${String(req.params.id)} not found`);
    return s;
  };

  app.get("/health", (_req, res) => {
    res.json({ ok: true, apps: [...manifests.keys()], sessions: sessions.size });
  });

  app.post("/sessions", async (req, res) => {
    const b = Body.createSession.parse(req.body);
    const manifest = manifests.get(b.app);
    if (!manifest) throw new SandboxError(404, "unknown_app", `app ${b.app} is not configured`);
    const s = await Session.create(await getBrowser(), manifest, { ...(b.seed === undefined ? {} : { seed: b.seed }), ...(b.leak ? { leak: b.leak } : {}) });
    sessions.set(s.id, s);
    res.json({ session_id: s.id, app: manifest.app, base_url: manifest.base_url });
  });

  app.post("/sessions/:id/reset", async (req, res) => {
    await session(req).reset(Body.reset.parse(req.body ?? {}).seed);
    res.json({ ok: true });
  });

  app.delete("/sessions/:id", async (req, res) => {
    const s = session(req);
    sessions.delete(s.id);
    await s.close();
    res.json({ ok: true });
  });

  app.put("/sessions/:id/tools", (req, res) => {
    const b = Body.tools.parse(req.body);
    let count: number;
    try {
      count = session(req).loadTools(b.tools as ToolDefinition[], b.contracts as ToolContract[]);
    } catch (err) {
      if (err instanceof SandboxError) throw err;
      throw new SandboxError(400, "invalid_record", (err as Error).message);
    }
    res.json({ ok: true, count });
  });

  app.post("/sessions/:id/invoke", async (req, res) => {
    const b = Body.invoke.parse(req.body);
    res.json(await session(req).invoke(b.tool_id, b.args, { source: b.source, ...(b.post_observe_ms === undefined ? {} : { postObserveMs: b.post_observe_ms }), screenshot: b.screenshot ?? false }));
  });

  app.post("/sessions/:id/invoke_concurrent", async (req, res) => {
    const b = Body.concurrent.parse(req.body);
    res.json(await session(req).invokeConcurrent(b.calls, { source: b.source, ...(b.post_observe_ms === undefined ? {} : { postObserveMs: b.post_observe_ms }) }));
  });

  app.post("/sessions/:id/replay", async (req, res) => {
    res.json(await session(req).replay(Body.replay.parse(req.body).run_id));
  });

  app.get("/sessions/:id/events", (req, res) => {
    res.json({ events: session(req).events(Number(req.query.since_seq ?? 0)) });
  });

  app.get("/sessions/:id/state", async (req, res) => {
    res.json(await session(req).state({ screenshot: req.query.screenshot === "true" || req.query.screenshot === "1" }));
  });

  app.post("/sessions/:id/dom_action", async (req, res) => {
    res.json(await session(req).domAction(Body.domAction.parse(req.body) as DomAction));
  });

  app.get("/sessions/:id/example_args", async (req, res) => {
    const seed = req.query.seed === undefined ? undefined : Number(req.query.seed);
    res.json(await session(req).exampleArgs(String(req.query.tool_id ?? ""), seed));
  });

  app.post("/sessions/:id/apply", async (req, res) => {
    await session(req).apply(Body.apply.parse(req.body).state);
    res.json({ ok: true });
  });

  app.post("/sessions/:id/inject_leak", async (req, res) => {
    const b = Body.leak.parse(req.body);
    await session(req).injectLeak(b.kind, b.delay_ms);
    res.json({ ok: true });
  });

  app.use((req, res) => {
    res.status(404).json({ error: { code: "not_found", message: `no route ${req.method} ${req.path}` } });
  });

  app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if ((err as { type?: string }).type === "entity.parse.failed") return res.status(400).json({ error: { code: "bad_request", message: "request body is not valid JSON" } });
    if (err instanceof ZodError) return res.status(400).json({ error: { code: "bad_request", message: err.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ") } });
    if (err instanceof SandboxError) return res.status(err.status).json({ error: { code: err.code, message: err.message } });
    log("sandbox").error("unhandled", { message: (err as Error).message, stack: (err as Error).stack });
    res.status(500).json({ error: { code: "internal", message: (err as Error).message } });
  });

  return {
    app,
    async close() {
      for (const s of sessions.values()) await s.close().catch(() => undefined);
      sessions.clear();
      if (browser) await (await browser).close();
    },
  };
}

export function loadManifests(): AppManifest[] {
  return fs
    .readdirSync(SEED_APPS_DIR)
    .map((d) => path.join(SEED_APPS_DIR, d, "app.json"))
    .filter((f) => fs.existsSync(f))
    .map((f) => JSON.parse(fs.readFileSync(f, "utf8")) as AppManifest);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const port = Number(process.env.SPECX_SANDBOX_PORT ?? 4000);
  const sandbox = createSandbox({ manifests: loadManifests() });
  const server = sandbox.app.listen(port, "127.0.0.1", () => log("sandbox").info("listening", { url: `http://127.0.0.1:${port}` }));
  const stop = async () => {
    server.close();
    await sandbox.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void stop());
  process.on("SIGTERM", () => void stop());
}
