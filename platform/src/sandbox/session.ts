/**
 * One sandbox session: a Playwright browser context logged into one seed app as its own tenant, a tool
 * set, and the run history needed for sequence prefixes and replay. Every mutating operation is
 * serialised per session so concurrent HTTP calls cannot interleave runs.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import type { Browser, BrowserContext, Page } from "playwright";
import { exampleArgs, type ExampleArgs } from "../contracts/args.js";
import type { DomProbe, RunContext } from "../contracts/checkers.js";
import type { AppManifest, AuditRow, DbSnapshot, EventRecord, Mode, Source, ToolContract, ToolDefinition, Verdict } from "../contracts/types.js";
import { validate } from "../contracts/validate.js";
import { log } from "../log.js";
import { ensureParent, eventsPath, repoRelative, screenshotPath, verdictsPath } from "../paths.js";
import { observe, refHandle } from "./aria.js";
import { buildEffectDiff, evaluatePreconditions, evaluateRun, type Evaluated } from "./effects.js";
import { SandboxError } from "./errors.js";
import { observeContext, observePage } from "./observe.js";
import { EventRecorder } from "./recorder.js";

const HANDLER_TIMEOUT_MS = 10_000;
const LEAK_KINDS = ["delayed_post", "storage_write", "third_party_fetch", "background_poll"] as const;
type Args = Record<string, unknown>;
interface Call {
  tool_id: string;
  args: Args;
  /** Page a ui tool ran on (resolved before the run), so replay reopens exactly that page. */
  page?: string;
}
/** Everything since the last reset that shaped the state a run started from; replay re-applies it. */
type Step = { kind: "calls"; calls: Call[] } | { kind: "apply"; state: Record<string, unknown> } | { kind: "leak"; leak: string; delayMs: number };
interface RunRecord {
  call: Call;
  prefix: Step[];
  seed: number;
  source: Source;
  postObserveMs: number;
}
export interface InvokeOptions {
  source: Source;
  postObserveMs?: number;
  screenshot?: boolean;
  /** Concrete page for a page-scoped (ui) tool; defaults to the tool's pattern filled from the DB. */
  page?: string;
}
export type DomAction = { action: "click"; ref: string } | { action: "type"; ref: string; text: string } | { action: "press"; key: string } | { action: "navigate"; url: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const log_ = log("sandbox");

export class Session {
  readonly id = `s_${crypto.randomUUID().slice(0, 8)}`;
  private context!: BrowserContext;
  private page!: Page;
  private extraPages: Page[] = [];
  private readonly pageRun = new Map<Page, string>();
  private readonly recorder: EventRecorder;
  private tools = new Map<string, ToolDefinition>();
  private contracts = new Map<string, ToolContract>();
  private history: Step[] = [];
  private readonly runs = new Map<string, RunRecord>();
  private resetSeed = 0;
  private counter = 0;
  private chain: Promise<unknown> = Promise.resolve();

  private constructor(
    private readonly browser: Browser,
    readonly manifest: AppManifest,
  ) {
    const file = ensureParent(eventsPath(this.id));
    this.recorder = new EventRecorder(this.id, { sink: (e) => fs.appendFileSync(file, `${JSON.stringify(e)}\n`) });
  }

  static async create(browser: Browser, manifest: AppManifest, opts: { seed?: number; leak?: { kind: string; delay_ms: number } } = {}): Promise<Session> {
    const s = new Session(browser, manifest);
    s.context = await browser.newContext({ baseURL: manifest.base_url });
    await s.context.addCookies([{ name: "specx_tenant", value: s.id, url: manifest.base_url }]);
    await observeContext(s.context, manifest, (page, kind, data) => s.onEvent(page, kind, data));
    s.page = await s.newPage();
    await s.resetNow(opts.seed ?? 0);
    if (opts.leak) await s.hook("POST", "/__test/leak", opts.leak);
    log_.info("session created", { session: s.id, app: manifest.app });
    return s;
  }

  // ------------------------------------------------------------------ plumbing
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const next = this.chain.then(fn, fn);
    this.chain = next.catch(() => undefined);
    return next;
  }

  private async newPage(): Promise<Page> {
    const page = await this.context.newPage();
    observePage(page, this.manifest, (p, kind, data) => this.onEvent(p, kind, data));
    return page;
  }

  private snapshotHistory(): Step[] {
    return this.history.map((s) => (s.kind === "calls" ? { kind: "calls", calls: s.calls.map((c) => ({ ...c })) } : { ...s }));
  }

  private prefixToolIds(prefix: Step[]): string[] {
    return prefix.flatMap((s) => (s.kind === "calls" ? s.calls.map((c) => c.tool_id) : []));
  }

  /** At least `n` extra pages, each loaded on the app so relative fetches in handlers resolve. */
  private async extraPagesFor(n: number): Promise<Page[]> {
    while (this.extraPages.length < n) {
      const p = await this.newPage();
      await p.goto(this.manifest.home_path ?? "/");
      this.extraPages.push(p);
    }
    return this.extraPages.slice(0, n);
  }

  /** The concrete page a page-scoped tool must run on, or null for tools that run on any page. */
  private async pageFor(tool: ToolDefinition, requested?: string): Promise<string | null> {
    const pattern = tool.handler.page;
    if (tool.handler.kind !== "ui" && (!pattern || pattern === "*")) return null;
    if (requested) return requested;
    if (!pattern || pattern === "*") return tool.handler.page_example ?? null;
    const segs = pattern.split("/");
    if (!segs.some((s) => s.startsWith(":"))) return pattern;
    const db = await this.db();
    const filled = segs.map((seg, i) => {
      if (!seg.startsWith(":")) return seg;
      const rows = db[segs[i - 1] ?? ""]?.rows ?? [];
      return rows.length ? String(rows.at(-1)?.id) : null;
    });
    return filled.every((s) => s !== null) ? filled.join("/") : (tool.handler.page_example ?? null);
  }

  private async open(page: Page, target: string | null | undefined): Promise<void> {
    if (target) await page.goto(target);
  }

  private onEvent(page: Page | null, kind: EventRecord["kind"], data: Record<string, unknown>): void {
    this.recorder.record(kind, data, page ? this.pageRun.get(page) : undefined);
  }

  private async hook<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.manifest.base_url + path, {
      method,
      headers: { "x-specx-tenant": this.id, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new SandboxError(502, "app_error", `${method} ${path} -> ${res.status} ${await res.text()}`);
    return (await res.json()) as T;
  }

  private async db(): Promise<DbSnapshot> {
    return (await this.hook<{ tables: DbSnapshot }>("GET", "/__test/db")).tables;
  }

  private userOf(db: DbSnapshot): { id: unknown } | null {
    const row = db.users?.rows.find((r) => r.username === this.manifest.auth.username);
    return row ? { id: row.id } : null;
  }

  private probe(page: Page): DomProbe {
    return {
      url: () => page.url(),
      count: (s) => page.locator(s).count(),
      text: (s) => page.locator(s).first().innerText({ timeout: 1000 }).catch(() => ""),
    };
  }

  private tool(toolId: string): { tool: ToolDefinition; contract: ToolContract } {
    const tool = this.tools.get(toolId);
    const contract = this.contracts.get(toolId);
    if (!tool || !contract) throw new SandboxError(404, "unknown_tool", `tool ${toolId} is not loaded in session ${this.id}`);
    return { tool, contract };
  }

  private async runHandler(page: Page, code: string, args: Args): Promise<{ output: unknown; error: string | null }> {
    let timer: NodeJS.Timeout | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`handler timed out after ${HANDLER_TIMEOUT_MS} ms`)), HANDLER_TIMEOUT_MS);
    });
    try {
      const output = await Promise.race([page.evaluate(([c, input]) => (0, eval)(c as string)(input) as unknown, [code, args] as const), timeout]);
      return { output: output ?? null, error: null };
    } catch (err) {
      return { output: null, error: (err as Error).message.split("\n")[0] ?? "handler error" };
    } finally {
      clearTimeout(timer);
    }
  }

  private newAudit(before: DbSnapshot, after: DbSnapshot): AuditRow[] {
    const seen = new Set((before[this.manifest.audit_table]?.rows ?? []).map((r) => r.id));
    return (after[this.manifest.audit_table]?.rows ?? []).filter((r) => !seen.has(r.id)) as unknown as AuditRow[];
  }

  private emitAudit(rows: AuditRow[], runId: string, emitted: Set<unknown>): void {
    for (const a of rows) {
      if (emitted.has(a.id)) continue;
      emitted.add(a.id);
      this.recorder.record("audit", { event: a.event, actor: a.actor, entity: a.entity, entity_id: a.entity_id }, runId);
    }
  }

  private async resetNow(seed: number): Promise<void> {
    await this.hook("POST", "/__test/reset", { seed });
    this.recorder.clear();
    this.pageRun.clear();
    for (const p of this.extraPages) await p.close();
    this.extraPages = [];
    this.history = [];
    this.resetSeed = seed;
    const login = await this.context.request.post(this.manifest.base_url + "/api/login", {
      data: { username: this.manifest.auth.username, password: this.manifest.auth.password },
    });
    if (!login.ok()) throw new SandboxError(502, "login_failed", `login as ${this.manifest.auth.username} failed: ${login.status()}`);
    await this.page.goto(this.manifest.home_path ?? "/");
    await this.page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  }

  private persist(v: Verdict): Verdict {
    validate("verdict", v);
    fs.appendFileSync(ensureParent(verdictsPath(v.source)), `${JSON.stringify(v)}\n`);
    return v;
  }

  /** The session's main page. Only the F3 crawler uses this, to listen to request/response bodies. */
  crawlerPage(): Page {
    return this.page;
  }

  // ------------------------------------------------------------------ public API (contracts/sandbox_api.md)
  loadTools(tools: ToolDefinition[], contracts: ToolContract[]): number {
    for (const t of tools) validate("tool_definition", t);
    for (const c of contracts) validate("contract", c);
    const byId = new Map(contracts.map((c) => [c.tool_id, c]));
    const missing = tools.filter((t) => !byId.has(t.tool_id)).map((t) => t.tool_id);
    if (missing.length) throw new SandboxError(400, "missing_contract", `no contract for ${missing.join(", ")}`);
    this.tools = new Map(tools.map((t) => [t.tool_id, t]));
    this.contracts = byId;
    return tools.length;
  }

  reset(seed?: number): Promise<void> {
    return this.serial(() => this.resetNow(seed ?? this.resetSeed));
  }

  invoke(toolId: string, args: Args, opts: InvokeOptions): Promise<Verdict> {
    return this.serial(() => this.invokeNow(toolId, args, opts, "single"));
  }

  private async invokeNow(toolId: string, args: Args, opts: InvokeOptions, mode: Exclude<Mode, "concurrent">): Promise<Verdict> {
    const { tool, contract } = this.tool(toolId);
    const postObserveMs = opts.postObserveMs ?? 1500;
    const pagePath = await this.pageFor(tool, opts.page);
    await this.open(this.page, pagePath);
    const runId = `${this.id}_r${++this.counter}`;
    const prefix = this.snapshotHistory();
    const started = new Date();
    const t0 = performance.now();
    const urlBefore = this.page.url();
    const dbBefore = await this.db();
    const user = this.userOf(dbBefore);
    const pre = await evaluatePreconditions(contract, { manifest: this.manifest, toolId, args, output: null, user, dbBefore, dbAfter: dbBefore, newAudit: [], events: [], dom: this.probe(this.page) });
    this.pageRun.clear();
    this.recorder.begin([runId]);
    this.recorder.setPhase("during");
    this.recorder.record("tool_start", { tool_id: toolId, args, mode, ...(pagePath ? { page: pagePath } : {}) });
    const { output, error } = await this.runHandler(this.page, tool.handler.code, args);
    this.recorder.record("tool_end", { status: error ? "error" : "ok", output, error });
    this.recorder.setPhase("post");
    const emitted = new Set<unknown>();
    const early = await this.hook<{ events: AuditRow[] }>("GET", `/__test/audit?since=${Math.max(0, ...(dbBefore[this.manifest.audit_table]?.rows ?? []).map((r) => Number(r.id)))}`);
    this.emitAudit(early.events, runId, emitted);
    await sleep(postObserveMs);
    const dbAfter = await this.db();
    const newAudit = this.newAudit(dbBefore, dbAfter);
    this.emitAudit(newAudit, runId, emitted);
    const events = this.recorder.eventsFor(runId);
    const ctx: RunContext = { manifest: this.manifest, toolId, args, output, user, dbBefore, dbAfter, newAudit, events, dom: this.probe(this.page) };
    const ev = await evaluateRun(contract, ctx, { mode, handlerError: error, pre });

    const call: Call = { tool_id: toolId, args, ...(pagePath ? { page: pagePath } : {}) };
    this.history.push({ kind: "calls", calls: [call] });
    this.runs.set(runId, { call, prefix, seed: this.resetSeed, source: opts.source, postObserveMs });
    const verdict: Verdict = {
      run_id: runId,
      session_id: this.id,
      app: this.manifest.app,
      tool_id: toolId,
      tool_version: tool.version,
      metadata_revision: tool.metadata_revision,
      args,
      mode,
      sequence_prefix: this.prefixToolIds(prefix),
      started_at: started.toISOString(),
      duration_ms: Math.round(performance.now() - t0),
      status: ev.status,
      output,
      clause_results: ev.clause_results,
      effect_diff: buildEffectDiff({ events, dbBefore, dbAfter, newAudit, urlBefore, urlAfter: this.page.url() }),
      violations: ev.violations,
      anomaly: null,
      source: opts.source,
      artifacts: { events_path: repoRelative(eventsPath(this.id)) },
    };
    if (opts.screenshot) {
      const file = ensureParent(screenshotPath(runId));
      await this.page.screenshot({ path: file });
      verdict.artifacts = { ...verdict.artifacts, screenshot_path: repoRelative(file) };
    }
    return this.persist(verdict);
  }

  invokeConcurrent(calls: Call[], opts: InvokeOptions): Promise<{ concurrency_group: string; verdicts: Verdict[] }> {
    return this.serial(async () => {
      const resolved = calls.map((c) => ({ ...c, ...this.tool(c.tool_id) }));
      const postObserveMs = opts.postObserveMs ?? 1500;
      const group = `${this.id}_g${++this.counter}`;
      const runIds = calls.map(() => `${this.id}_r${++this.counter}`);
      const pages = await this.extraPagesFor(calls.length);
      const targets = await Promise.all(resolved.map((c) => this.pageFor(c.tool, c.page)));
      for (const [i, target] of targets.entries()) await this.open(pages[i] as Page, target);
      const prefix = this.snapshotHistory();
      const started = new Date();
      const t0 = performance.now();
      const dbBefore = await this.db();
      const user = this.userOf(dbBefore);
      const pres: Evaluated[][] = [];
      for (const [i, c] of resolved.entries()) {
        pres.push(await evaluatePreconditions(c.contract, { manifest: this.manifest, toolId: c.tool_id, args: c.args, output: null, user, dbBefore, dbAfter: dbBefore, newAudit: [], events: [], dom: this.probe(pages[i] as Page) }));
      }
      this.pageRun.clear();
      pages.forEach((p, i) => this.pageRun.set(p, runIds[i] as string));
      this.recorder.begin(runIds);
      this.recorder.setPhase("during");
      resolved.forEach((c, i) => this.recorder.record("tool_start", { tool_id: c.tool_id, args: c.args, mode: "concurrent" }, runIds[i]));
      // Each call enters its post phase as soon as its own handler returns.
      const results = await Promise.all(
        resolved.map(async (c, i) => {
          const r = await this.runHandler(pages[i] as Page, c.tool.handler.code, c.args);
          this.recorder.record("tool_end", { status: r.error ? "error" : "ok", output: r.output, error: r.error }, runIds[i]);
          this.recorder.setPhase("post", runIds[i]);
          return r;
        }),
      );
      await sleep(postObserveMs);
      const dbAfter = await this.db();
      const newAudit = this.newAudit(dbBefore, dbAfter);
      this.emitAudit(newAudit, runIds[0] as string, new Set());
      const verdicts: Verdict[] = [];
      for (const [i, c] of resolved.entries()) {
        const runId = runIds[i] as string;
        const page = pages[i] as Page;
        const events = this.recorder.eventsFor(runId);
        const r = results[i] as { output: unknown; error: string | null };
        const ctx: RunContext = { manifest: this.manifest, toolId: c.tool_id, args: c.args, output: r.output, user, dbBefore, dbAfter, newAudit, events, dom: this.probe(page), group: { dbBefore, dbAfter } };
        const ev = await evaluateRun(c.contract, ctx, { mode: "concurrent", handlerError: r.error, pre: pres[i] as Evaluated[] });
        const target = targets[i];
        this.runs.set(runId, { call: { tool_id: c.tool_id, args: c.args, ...(target ? { page: target } : {}) }, prefix, seed: this.resetSeed, source: opts.source, postObserveMs });
        verdicts.push(
          this.persist({
            run_id: runId,
            session_id: this.id,
            app: this.manifest.app,
            tool_id: c.tool_id,
            tool_version: c.tool.version,
            metadata_revision: c.tool.metadata_revision,
            args: c.args,
            mode: "concurrent",
            concurrency_group: group,
            sequence_prefix: this.prefixToolIds(prefix),
            started_at: started.toISOString(),
            duration_ms: Math.round(performance.now() - t0),
            status: ev.status,
            output: r.output,
            clause_results: ev.clause_results,
            effect_diff: buildEffectDiff({ events, dbBefore, dbAfter, newAudit, urlBefore: page.url(), urlAfter: page.url() }),
            violations: ev.violations,
            anomaly: null,
            source: opts.source,
            artifacts: { events_path: repoRelative(eventsPath(this.id)) },
          }),
        );
      }
      this.history.push({ kind: "calls", calls: calls.map((c, i) => ({ tool_id: c.tool_id, args: c.args, ...(targets[i] ? { page: targets[i] as string } : {}) })) });
      return { concurrency_group: group, verdicts };
    });
  }

  /** Reset to the run's seed, silently re-run its prefix, then re-invoke the same call. */
  replay(runId: string): Promise<Verdict> {
    return this.serial(async () => {
      const rec = this.runs.get(runId);
      if (!rec) throw new SandboxError(404, "unknown_run", `run ${runId} not found in session ${this.id}`);
      await this.resetNow(rec.seed);
      for (const step of rec.prefix) {
        if (step.kind === "apply") await this.hook("POST", "/__test/apply", { state: step.state });
        else if (step.kind === "leak") await this.hook("POST", "/__test/leak", { kind: step.leak, delay_ms: step.delayMs });
        else {
          const pages = step.calls.length === 1 ? [this.page] : await this.extraPagesFor(step.calls.length);
          for (const [i, c] of step.calls.entries()) await this.open(pages[i] as Page, c.page);
          await Promise.all(step.calls.map((c, i) => this.runHandler(pages[i] as Page, this.tool(c.tool_id).tool.handler.code, c.args)));
        }
        this.history.push(step);
      }
      return this.invokeNow(rec.call.tool_id, rec.call.args, { source: rec.source, postObserveMs: rec.postObserveMs, ...(rec.call.page ? { page: rec.call.page } : {}) }, "replay");
    });
  }

  events(sinceSeq: number): EventRecord[] {
    return this.recorder.since(sinceSeq);
  }

  state(opts: { screenshot?: boolean } = {}): Promise<Record<string, unknown>> {
    return this.serial(async () => ({
      url: this.page.url(),
      db: await this.db(),
      storage: await this.page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } })),
      aria: await observe(this.page),
      ...(opts.screenshot ? { screenshot_b64: (await this.page.screenshot()).toString("base64") } : {}),
    }));
  }

  /** Raw-DOM agent step. Recorded as its own run (`<session>_a<n>`) so its network effects are observable. */
  domAction(a: DomAction): Promise<{ ok: true; run_id: string; aria: string; url: string }> {
    return this.serial(async () => {
      const runId = `${this.id}_a${++this.counter}`;
      this.pageRun.clear();
      this.recorder.begin([runId]);
      this.recorder.setPhase("during");
      switch (a.action) {
        case "navigate": {
          const target = new URL(a.url, this.manifest.base_url);
          if (target.origin !== new URL(this.manifest.base_url).origin) throw new SandboxError(400, "scope_exceeded", `navigation outside ${this.manifest.base_url} is not allowed`);
          await this.page.goto(target.href);
          break;
        }
        case "click":
          await (await refHandle(this.page, a.ref)).click({ timeout: 5000 });
          break;
        case "type":
          await (await refHandle(this.page, a.ref)).fill(a.text, { timeout: 5000 });
          break;
        case "press":
          await this.page.keyboard.press(a.key);
          break;
      }
      await sleep(300); // let fetch-driven reloads start
      await this.page.waitForLoadState("domcontentloaded").catch(() => undefined);
      this.recorder.setPhase("post");
      return { ok: true as const, run_id: runId, aria: await observe(this.page), url: this.page.url() };
    });
  }

  exampleArgs(toolId: string, seed?: number): Promise<ExampleArgs> {
    return this.serial(async () => {
      const { tool, contract } = this.tool(toolId);
      const db = await this.db();
      return exampleArgs(tool, contract, db, this.userOf(db), seed === undefined ? {} : { seed });
    });
  }

  apply(state: Record<string, unknown>): Promise<void> {
    return this.serial(async () => {
      await this.hook("POST", "/__test/apply", { state });
      this.history.push({ kind: "apply", state });
    });
  }

  injectLeak(kind: string, delayMs: number): Promise<void> {
    if (!(LEAK_KINDS as readonly string[]).includes(kind)) throw new SandboxError(400, "bad_leak_kind", `unknown leak kind ${kind}`);
    return this.serial(async () => {
      await this.hook("POST", "/__test/leak", { kind, delay_ms: delayMs });
      this.history.push({ kind: "leak", leak: kind, delayMs });
    });
  }

  async close(): Promise<void> {
    await this.serial(() => this.context.close());
  }
}
