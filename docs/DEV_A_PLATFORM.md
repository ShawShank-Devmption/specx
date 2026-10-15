# Dev A — Platform Implementation Plan (seed apps · F3 generation · F1 contracts · sandbox · graph · CLI/CI)

> **For agentic workers:** execute task-by-task in order with `superpowers:executing-plans` (or subagent-driven). Each task ends with a passing test and a commit on branch `dev-a/<task-id>-<slug>`. Read `docs/00_PROJECT_CONTEXT.md` and `contracts/` first. Steps use `- [ ]` checkboxes.

**Goal:** by H8 the sandbox, generated tools, contracts, verdicts and workflow graphs for `shop` and `admin` exist on `main`, validated, deterministic, fast enough for ~15 k invokes; by H12 `make demo` runs the whole pipeline from a clean clone.

**Architecture:** TypeScript/Node 22 ESM. Two Express+SQLite seed apps with test hooks. A sandbox HTTP server (Express) that owns Playwright Chromium contexts, observes via CDP + injected observers, executes tool handlers in page context, evaluates contract clauses and emits `Verdict`/`EventRecord` JSON. A generator that mines routes, DOM/ARIA and network traces into atomic tools and asks Claude Opus 5.5 only for names/descriptions. A deterministic graph builder. A CLI.

**Tech stack:** `express`, `better-sqlite3`, `playwright` (Chromium + CDP), `ajv` + `ajv-formats`, `zod`, `tree-sitter-javascript` (fallback: regex), `@anthropic-ai/sdk`, `tsx`, `vitest`, `eslint`.

**Spec:** `docs/00_PROJECT_CONTEXT.md` §7 (seed apps), §8 (stages), `contracts/sandbox_api.md`, `contracts/README.md` (clause kinds).

## Global constraints

- Node ≥ 22, ESM, `strict` TS, `noUncheckedIndexedAccess`, no `any`.
- Every HTTP body validated with zod; every emitted record validated with `validate(name, obj)` (ajv) **before** writing.
- Ports: shop 5101, admin 5102, sandbox 4000. Seed-app DB file = `live.db` (gitignored), reset = copy `seed.db` → `live.db`.
- `post_observe_ms` default 1500; S1 passes 300. `invoke` ≤ 400 ms p50 for `api` handlers excluding observe window.
- ≥ 8 concurrent sessions per sandbox process (one Chromium browser, one context per session).
- Third-party requests are blocked **and** recorded. Nothing ever leaves localhost.
- Logging: `src/log.ts` → JSON lines on stderr. No `console.log` outside `cli/`.
- Commit after every task; PR per task; never commit `live.db`, `node_modules`, `results/`.

## Review focus (tests added in the owning task)

1. **Replay non-determinism from autoincrement ids** — `effect_diff.db` must compare *counts*, and `normalised_observed` must strip ids/timestamps, or replay fails spuriously. (A3 test `replay_identical`.)
2. **Post-phase events attributed to the wrong run** — events after `tool_end` must carry the finished `run_id` with `phase:"post"` until the next `tool_start`. (A3 test `post_phase_attribution`.)
3. **Concurrent invocations sharing one page corrupt each other's network attribution** — `invoke_concurrent` must tag requests by `concurrency_group` and evaluate `at_most_once` over the group. (A6 test `concurrent_race_detected`.)
4. **`approved` computed on path with query string or trailing slash** — normalise path before matching `:param` patterns. (A2 test `approved_path_matching`.)
5. **Generator emits a non-atomic tool** (e.g. "add and checkout") — emit must reject candidates that touch > 1 state-changing endpoint. (A4 test `emit_rejects_non_atomic`.)

---

### Task A0 (H0, 15 min): toolchain + skeleton compiles

**Files:** `platform/eslint.config.js`, `platform/src/log.ts`, `platform/src/paths.ts`, `platform/tests/smoke.test.ts`, `platform/scripts/start-apps.mjs` (stub that execs both servers).

- [ ] `cd platform && npm install && npx playwright install chromium`. If `tree-sitter` native build fails, remove it from `package.json` and note "regex route parser" in `docs/DECISIONS.md`.
- [ ] `src/paths.ts`: `export const RESULTS = path.resolve(process.env.SPECX_ROOT ?? "..", process.env.SPECX_RESULTS_DIR ?? "results")` and helpers `toolsPath(app)`, `contractsPath(app)`, `verdictsPath(source)`, `eventsPath(session)`, `graphPath(app)`; `ensureDirs()`.
- [ ] `src/log.ts`: `export const log = (mod: string) => ({info, warn, error})` writing `JSON.stringify({ts, level, mod, msg, ...fields})` to stderr.
- [ ] `tests/smoke.test.ts`: `expect(1+1).toBe(2)`; `npm test`, `npm run typecheck`, `npm run lint` all green.
- [ ] Commit `chore(platform): toolchain skeleton`.

### Task A1 (H0–H2): seed apps `shop` and `admin` with test hooks

**Files:** `platform/seed-apps/_lib/db.js` (open/reset/snapshot/audit helpers shared by both apps), `platform/seed-apps/_lib/leak.js`, `platform/seed-apps/_lib/testhooks.js`, `platform/seed-apps/shop/{server.js,schema.sql,seed.sql,app.json,public/app.js,views/*.html}`, same for `admin`, `platform/scripts/start-apps.mjs`, `platform/scripts/build-seed-db.mjs`, `platform/tests/seedapps.test.ts`.

**Interfaces produced:** the HTTP surface in CONTEXT §7 and `contracts/sandbox_api.md` (test hooks). `app.json` validates against `app_manifest.schema.json` (copy `fixtures/apps/shop.app.json` as the start; write `admin/app.json` by analogy with risk levels: GET=read, POST users=write, PATCH=write, role=write, DELETE=delete).

- [ ] `schema.sql` + `seed.sql` per app exactly as CONTEXT §7 (tables, seed rows, `audit_log(id INTEGER PRIMARY KEY, event TEXT, actor TEXT, entity TEXT, entity_id TEXT, ts TEXT)`). `scripts/build-seed-db.mjs` builds `seed.db` from them (run on `npm run apps` if missing).
- [ ] `_lib/db.js`: `openLive(appDir)`, `reset(appDir)` (close, `fs.copyFileSync(seed.db, live.db)`, reopen), `snapshot(db, tables)` → `{table: {count, rows}}`, `audit(db, event, actor, entity, entityId)`.
- [ ] `_lib/testhooks.js`: mounts `/__test/reset|db|audit|leak|apply` on an Express app given `{db, tables, applyState}`. `/__test/apply` for shop supports `{cart:[{product_id,qty}]}`; for admin `{users:[...]}`.
- [ ] `_lib/leak.js`: `armLeak(kind, delayMs)`; middleware that, after the next mutating API response, sets `res.locals.leak`; the HTML layout includes `<script src="/__leak.js">` which returns an empty script unless armed, else the matching snippet (`delayed_post` / `storage_write` / `third_party_fetch` / `background_poll` from `sandbox_api.md`). One-shot: clears after serving.
- [ ] `shop/server.js`: pages and API per CONTEXT §7, cookie session (`express-session` or a hand-rolled signed cookie), **leave the three intentional defects in** (no transaction around order creation; no stock check; `POST /api/analytics` returning 204). Each mutating endpoint calls `audit(...)`. Every button/input has `data-testid` and an accessible name.
- [ ] `admin/server.js`: same pattern; defects: delete cascades to `notes` silently; PATCH allows deactivating the last admin; `/role` writes no audit row.
- [ ] Test `tests/seedapps.test.ts` (starts each server on a random port with `PORT` env): `reset` twice → identical `/__test/db` JSON; `POST /api/cart` increments `cart_items.count` and adds one `audit_log` row with `event:"cart.add"`; two parallel `POST /api/orders` after one add create **2** orders (documents the race); `POST /__test/leak {kind:"delayed_post",delay_ms:50}` then `POST /api/cart` then `GET /__leak.js` returns the analytics snippet once and empty the second time.
- [ ] Commit `feat(seed-apps): shop and admin with test hooks and intentional defects`. Open PR; **merge by H2** even if views are ugly.

### Task A2 (H1–H2): contract validation + clause checkers + example args

**Files:** `platform/src/contracts/validate.ts`, `platform/src/contracts/types.ts` (TS types mirroring the schemas; hand-written, kept small), `platform/src/contracts/match.ts` (endpoint pattern matching), `platform/src/contracts/checkers.ts`, `platform/src/contracts/args.ts`, tests next to each.

**Interfaces produced:**
```ts
// validate.ts
export type SchemaName = "app_manifest"|"tool_definition"|"contract"|"event_record"|"verdict"|"workflow_graph"|"task"|"trial_result"|"patch";
export function validate<T = unknown>(name: SchemaName, obj: unknown): T; // throws Error(`${name}${pointer}: ${message}`)
// match.ts
export function matchEndpoint(manifest: AppManifest, method: string, url: string): {approved: boolean; third_party: boolean; risk_level?: RiskLevel; path: string};
// checkers.ts
export interface RunContext { page: Page; manifest: AppManifest; args: Record<string, unknown>; output: unknown;
  dbBefore: DbSnapshot; dbAfter: DbSnapshot; auditBefore: number; auditAfter: AuditRow[];
  events: EventRecord[]; /* during + post for this run */ concurrencyGroup?: {dbBefore: DbSnapshot; dbAfter: DbSnapshot} }
export type Checker = (ctx: RunContext, params: Record<string, unknown>) => Promise<Omit<ClauseResult,"clause_id"|"surface"|"kind">>;
export const CHECKERS: Record<ClauseKind, Checker>;
export function dbDelta(before: DbSnapshot, after: DbSnapshot): EffectDiff["db"];
export function normaliseObserved(kind: ClauseKind, observed: unknown): string; // strips ids/timestamps → signature part
// args.ts
export function exampleArgs(tool: ToolDefinition, db: DbSnapshot): Record<string, unknown>; // valid args from live state
```

- [ ] `validate.ts`: load all schemas from `../../contracts/*.schema.json` once; `Ajv2020({allErrors:true, strict:false})` + `addFormats`. Test: every file in `fixtures/` validates; a verdict with `status:"maybe"` throws with pointer `/status`.
- [ ] `match.ts`: normalise URL → path without query/trailing slash; `:param` segments match `[^/]+`. Tests: `/api/cart/3?x=1` matches `DELETE /api/cart/:product_id`; `/api/analytics` → `approved:false, third_party:false`; `https://tracker.example.invalid/p` → `third_party:true`.
- [ ] `checkers.ts`: implement all 14 kinds from `contracts/README.md` table. `$args.<name>` references in `params.where` resolve from `ctx.args`. `network_calls` counts events with `kind:"network_request"`, phase ∈ {during, post}. `at_most_once` uses `ctx.concurrencyGroup` when present else the run's own delta. Tests use hand-built `RunContext` objects (no browser): `db_delta` pass/fail, `network_calls` with max exceeded, `at_most_once` with group inserted=2 → fail, `storage_untouched` with a storage event → fail with observed list.
- [ ] `args.ts`: strategy per parameter name: `product_id`/`user_id`/`id` → first existing row id of the obvious table; `qty` → 1; `confirm` → true; `role` → "editor"; `username/email` → `"u_" + Date.now()`; strings → "test"; integers → 1; booleans → true. Test: for the fixture tools + a fixture db snapshot returns args that validate against each tool's `input_schema`.
- [ ] Commit `feat(contracts): validators, endpoint matching, clause checkers, example args`.

### Task A3 (H2–H3, **Gate 1**): sandbox server — sessions, reset, invoke, replay, events, state, dom_action

**Files:** `platform/src/sandbox/server.ts`, `session.ts`, `observe.ts`, `effects.ts`, `handlers.ts`, `tests/sandbox.integration.test.ts` (runs only with `SANDBOX_INTEGRATION=1`), `tests/sandbox.unit.test.ts`.

**Interfaces produced:** exactly `contracts/sandbox_api.md`. Internal:
```ts
// session.ts
export class Session {
  static async create(app: AppManifest, opts: {seed?: number; leak?: Leak}): Promise<Session>;
  loadTools(tools: ToolDefinition[], contracts: ToolContract[]): void;
  reset(seed?: number): Promise<void>;                      // POST /__test/reset + new page + login + clear storage + observers
  invoke(toolId: string, args: Rec, opts: {source: Source; postObserveMs: number; screenshot: boolean; group?: string}): Promise<Verdict>;
  invokeConcurrent(calls: {tool_id: string; args: Rec}[], opts): Promise<{concurrency_group: string; verdicts: Verdict[]}>;
  replay(runId: string): Promise<Verdict>;
  events(sinceSeq: number): EventRecord[];
  state(opts: {screenshot: boolean}): Promise<StateResponse>;
  domAction(a: DomAction): Promise<{ok: boolean; aria: string; url: string}>;
  exampleArgs(toolId: string): Promise<Rec>;
  close(): Promise<void>;
}
// observe.ts — attaches to a Page: CDP Network.* + Fetch.* (block third-party), addInitScript with MutationObserver + storage wrappers posting via page.exposeBinding("__specx_emit")
export function attachObservers(page: Page, sink: (e: Omit<EventRecord,"session_id"|"run_id"|"seq"|"t_ms"|"phase">) => void, manifest: AppManifest): Promise<void>;
// effects.ts
export function buildEffectDiff(ctx: RunContext): EffectDiff;
export function evaluateContract(ctx: RunContext, contract: ToolContract): Promise<{clause_results: ClauseResult[]; violations: Violation[]; status: Verdict["status"]}>;
```

- [ ] `observe.ts`: `Network.requestWillBeSent` → `network_request` with `matchEndpoint`; `Network.responseReceived` → `network_response`; `Fetch.enable({patterns:[{urlPattern:"*"}]})` and `Fetch.failRequest` when `third_party` (still emit the request event). Init script: `new MutationObserver(...)` batching per animation frame into one `dom_mutation` event with counts + first target selector; wrap `localStorage.setItem/removeItem/clear`, `sessionStorage.*`, and `document.cookie` setter → `storage` events; `console` → `console` events; `framenavigated` → `navigation`. Audit events come from polling `GET /__test/audit?since=` at `tool_end` and at the end of the observe window.
- [ ] `session.ts` run loop for `invoke`: `seq`/`t_ms` stamping; phases: `pre` (preconditions evaluated on `dbBefore`/page), `during` (handler runs via `page.evaluate(new Function("input", "return (" + code + ")(input)"), args)` with a 10 s timeout; errors → `status:"error"`), `post` (wait `postObserveMs`, then `dbAfter`, audit poll). Then `evaluateContract`, `buildEffectDiff`, `violations` with `signature = \`${tool_id}|${clause_id}|${kind}|${normaliseObserved(kind, observed)}\`` and `category` mapped from kind. `sequence_prefix` from session history. Store `{runId → {dbBefore, args, toolId}}` for replay. Validate the verdict with `validate("verdict", v)` before returning; append to `results/verdicts/<source>.jsonl` and events to `results/events/<session>.jsonl`.
- [ ] `server.ts`: Express routes per `sandbox_api.md`, zod-validated bodies, `api_version:"1"`, error envelope, `GET /health`. One shared `chromium.launch({headless:true})`, one `browser.newContext()` per session. Start with `tsx src/sandbox/server.ts`.
- [ ] `domAction`: ARIA snapshot via `page.locator("body").ariaSnapshot()`; assign `[ref=eN]` ids by walking `page.locator('[role], a, button, input, select, textarea')` (store `ref → locator`); `click` → `locator.click()`, `type` → `fill`, `press` → `keyboard.press`, `navigate` → only same-origin paths (reject others with `scope_exceeded`).
- [ ] Unit test (`sandbox.unit.test.ts`, no browser): phase attribution — a fake sink receiving events after `tool_end` tags them `phase:"post"` with the previous `run_id`; next `tool_start` switches run.
- [ ] Integration test (`SANDBOX_INTEGRATION=1`, apps running): create session for shop with fixture tools+contracts → `invoke shop.add_to_cart {product_id:1,qty:1}` → `status:"pass"`, `effect_diff.db.cart_items.inserted===1`; `replay(run_id)` → identical `clause_results[].passed` and identical `effect_diff.db` (**replay_identical**); inject leak `delayed_post` → next invoke `status:"fail"` with a violation whose `category==="unapproved_endpoint"` and the request event has `phase:"post"` (**post_phase_attribution**); `state()` returns ARIA containing "Add to cart".
- [ ] `make sandbox` works; `curl :4000/health` → `{ok:true}`. Commit `feat(sandbox): sessions, invoke, replay, events, state, dom_action`. **Merge = Gate 1.** Announce in channel.

### Task A4 (H3–H4.5): F3 generator — repo, DOM/ARIA, network, emit

**Files:** `platform/src/generator/repo.ts`, `dom.ts`, `network.ts`, `candidates.ts`, `emit.ts`, `llm.ts`, `index.ts`, tests for `repo`, `candidates`, `emit` (pure; LLM mocked).

**Interfaces produced:**
```ts
export interface RouteEvidence { method: HttpMethod; path: string; file: string; line: number; snippet: string; bodyFields: string[]; tablesWritten: string[]; tablesRead: string[]; writesAudit: string|null }
export function parseRoutes(appDir: string): RouteEvidence[];            // tree-sitter or regex over app.<verb>('path', …)
export interface DomEvidence { page: string; selector: string; role: string; name: string; testid?: string; formFields?: string[]; triggers?: {method: string; path: string} }
export async function crawlDom(manifest: AppManifest, session: Session): Promise<DomEvidence[]>;   // visits each page, clicks each button/submits each form in a reset state, records network via session.events()
export interface Candidate { name: string; route: RouteEvidence; dom: DomEvidence[]; network: {method: string; path: string}[]; risk_level: RiskLevel; inputFields: {name: string; type: "integer"|"string"|"boolean"; required: boolean}[]; outputFields: string[] }
export function buildCandidates(routes: RouteEvidence[], dom: DomEvidence[], manifest: AppManifest): Candidate[];
export async function emitTools(cands: Candidate[], manifest: AppManifest, llm: LlmNamer): Promise<ToolDefinition[]>;
export interface LlmNamer { (c: Candidate): Promise<{name: string; description: string; paramDescriptions: Record<string,string>}> }
```

- [ ] `repo.ts`: extract `app.get|post|patch|put|delete('<path>', handler)`; inside handler text, collect `req.body.<field>` → `bodyFields`, `INSERT INTO|UPDATE|DELETE FROM <table>` → `tablesWritten`, `SELECT … FROM <table>` → `tablesRead`, `audit(db, '<event>'` → `writesAudit`. Skip `/__test/*` and `/api/login`. Test on the real `shop/server.js`: 8 routes, `POST /api/cart` has `bodyFields ["product_id","qty"]`, `tablesWritten ["cart_items","audit_log"]`.
- [ ] `dom.ts`: for each page in the manifest's nav (derive from `<a href>` on `/`): snapshot ARIA, list `button|a|form`, click/submit each in a fresh reset and diff `session.events()` for network requests → `triggers`. Output fields come from the JSON of the triggered response (`Object.keys`), e.g. `{id,name,price_cents,stock}` for `GET /api/products/:id`.
- [ ] `candidates.ts`: one candidate per **state-changing route** and per **GET route** (reads are tools too); attach DOM evidence whose `triggers` match the route; `risk_level` from manifest; **reject** candidates whose DOM trigger fired > 1 state-changing endpoint (`emit_rejects_non_atomic` test with a synthetic "checkout-and-email" trigger). Input types from body fields + the example value types seen in traces.
- [ ] `llm.ts`: `claude-opus-5-5`, `output_config.effort:"high"`, `output_config.format` JSON schema `{name, description, paramDescriptions}`; system prompt states the naming rules (snake_case verb_noun, description ≤ 300 chars, mention data dependency on `list_*` for id parameters). Cache the system prompt with `cache_control`. Mocked in tests.
- [ ] `emit.ts`: build `ToolDefinition` with `handler.code` templated per route (`api` kind; `fetch` with JSON body / path params / query), `output_schema` from observed response keys, `provenance` entries: `code` (file:line + snippet), `dom` (selector), `aria` (`${role} '${name}'`), `network` (`METHOD /path`). `atomic:true`, `version:1`, `metadata_revision:0`. Validate each. Write `results/tools/<app>.tools.json`.
- [ ] Test: fixture-like candidate → tool validates; `shop.get_product` has `output_fields` containing `id`.
- [ ] Commit `feat(generator): evidence-based atomic tool emission`.

### Task A5 (H4.5–H5, **Gate 2**): F1 contract deriver + `verify` command

**Files:** `platform/src/contracts/derive.ts`, `platform/src/cli/main.ts`, `platform/src/cli/verify.ts`, `platform/src/cli/generate.ts`, tests `derive.test.ts`.

**Interfaces produced:**
```ts
export function deriveContract(tool: ToolDefinition, route: RouteEvidence, manifest: AppManifest, observed: Verdict|null): ToolContract;
// CLI
specx generate --app shop            → results/tools/shop.tools.json + results/contracts/shop.contracts.json
specx verify   --app shop [--runs 3] → results/verdicts/f1.jsonl ; sets status on tools file
```

- [ ] `derive.ts` rules: preconditions — `auth_state{logged_in:true}` for every non-login tool; `db_row_exists{table, where:{id:"$args.<id-param>"}}` for every id-typed param; `pre_cart_nonempty` style rules when `tablesRead` includes a table that must be non-empty for the route (`place_order` reads `cart_items`). Postconditions — `network_calls{method,path,min:1,max:1}`; `db_delta` per `tablesWritten` (`INSERT`→inserted:1, `DELETE`→deleted≥1 via `min`, `UPDATE`→updated:1); `db_delta{inserted:0,deleted:0}` for tables **not** in `tablesWritten` but in the manifest (this is what catches admin's hidden cascade on `notes`); `audit_event{event}` when `writesAudit`; `output_matches{schema: output_schema}`. Invariants — the three defaults + `at_most_once{table}` for `risk_level ∈ {payment, delete, write}` where the table is the inserted one; admin adds `db_row_exists{users, where:{role:"admin", active:1}}` as a postcondition for `update_user`/`deactivate_user` (encode as a rule: tables with a `role` column get a "keep one admin" postcondition).
- [ ] `verify.ts`: for each tool: 3 × `invoke` (fresh `exampleArgs` each, reset between) + 1 `replay` of the last + for write/delete/payment 1 × `invoke_concurrent` with 2 identical calls. Status: `verified` if all single runs `pass` and replay matches; `quarantined` if any `high` violation (incl. concurrent) or `error`; `unverifiable` if any clause `passed:null`. Quarantine reasons = the violation list. Rewrite `results/tools/<app>.tools.json` with `status`. Print a summary table.
- [ ] Test `derive.test.ts`: `shop.place_order` contract contains `inv_at_most_once` with `table:"orders"`; `admin.delete_user` contains `db_delta{table:"notes", deleted:0}`.
- [ ] Run `make generate && make verify` for both apps; expected: shop `place_order` quarantined (race), `add_to_cart` verified; admin `delete_user` quarantined (cascade), `set_role` quarantined (missing audit). Paste the summary into the PR. Commit `feat(cli): generate and verify`. **Merge = Gate 2.**

### Task A6 (H5–H8, **Gate 3**): graph builder, value-flow, concurrency hardening, throughput

**Files:** `platform/src/graph/build.ts`, `valueflow.ts`, `export.ts`, `platform/src/cli/graph.ts`, `tests/graph.test.ts`, changes in `session.ts`/`server.ts`.

**Interfaces produced:**
```ts
export function buildGraph(app: string, tools: ToolDefinition[], contracts: ToolContract[], verdicts: Verdict[]): WorkflowGraph;
export function valueFlowEdges(verdicts: Verdict[]): Edge[];  // evidence:"trace", label:true — output value of src appears later as an input value of dst within the same session
export function nameMatchEdges(tools: ToolDefinition[]): Edge[]; // evidence:"rule", label:null — same field name out→in
export function stateEdges(contracts: ToolContract[]): Edge[];   // evidence:"contract": src postcondition db_delta/inserted on T ⇒ dst precondition db_row_exists on T
export function orderEdges(verdicts: Verdict[]): Edge[];         // evidence:"trace": consecutive tool_ids in sequence_prefix (+ count-based confidence)
```

- [ ] `valueflow.ts`: for each session, keep a map `value → (tool_id, field)` from every verdict `output` (flatten one level, ignore booleans and values < 2 chars); when a later verdict's `args[field] === value`, emit a data edge `src→dst` with `field` = the **dst** param name, `label:true`. This recovers `get_product.id → add_to_cart.product_id` that name-matching misses. Test with three hand-built verdicts.
- [ ] `build.ts`: nodes from tools (fields from `input_schema.properties` / `output_schema.properties`; `state_reads/writes` from route evidence stored in provenance snippets — if not available, from contract tables); `violation_rate` from verdicts; merge edges (dedupe on `src,dst,type,field`, keep max confidence, `label:true` wins over null). Invariants: `requires` from state edges, `at_most_once`/`never_concurrent` from contract invariants. Validate; write `results/graphs/<app>.graph.json`.
- [ ] Throughput: `browser` shared; sessions created lazily; `invoke` must not `waitForLoadState` on api handlers; `post_observe_ms` honoured per request; measure `invoke` p50 with a 100-call loop in the integration test and assert < 400 ms (excluding observe window).
- [ ] `invoke_concurrent`: run handlers with `Promise.all` on the same page; tag requests arriving during the group with `concurrency_group`; compute group `dbBefore/dbAfter` once; `at_most_once` evaluated over the group. Integration test **`concurrent_race_detected`**: shop after one add_to_cart → `invoke_concurrent([place_order, place_order])` → both verdicts `fail` with a `category:"race"` violation and `effect_diff.db.orders.inserted === 2`.
- [ ] `example_args` endpoint backed by `args.ts` using a fresh `/__test/db` snapshot.
- [ ] Run `make graph`; paste node/edge counts in PR. Commit `feat(graph): typed workflow graph with value-flow edges; sandbox concurrency`. **Merge = Gate 3.**

### Task A7 (H8–H10): CLI polish, CI, run docs, reproducibility

**Files:** `platform/src/cli/main.ts`, `README.md` (root, "Run it" section), `.github/workflows/ci.yml` (already present — make it green), `scripts/run_all.sh`.

- [ ] `specx` CLI (`npm run cli --`): `generate|verify|graph` with `--app`, `--runs`, `--out`; `--help`; non-zero exit on validation failure. Pretty summary tables to stdout; JSON logs to stderr.
- [ ] `scripts/run_all.sh`: starts apps + sandbox in the background with health polling, runs `make demo`, stops processes on exit (`trap`). Document in README.
- [ ] CI green on your PR (lint, typecheck, unit tests; integration tests are skipped without `SANDBOX_INTEGRATION`).
- [ ] Freeze versions: pin `playwright` exact version in `package.json`; record Chromium version in `results/final/run.json` (via `browser.version()`).
- [ ] Commit `chore: cli polish, ci green, run_all script`.

### Task A8 (only if ahead at H8): third seed app `blog`

Posts/comments CRUD (`posts`, `comments`, `audit_log`), one defect (`DELETE /api/posts/:id` leaves orphan comments). Same files as A1. Register in `start-apps.mjs`, add to the Makefile app lists. Otherwise skip and note in `DECISIONS.md`.

### Task A9 (H10–H12): integration

- [ ] Clean clone → `make setup && make apps & make sandbox & make demo && make report` passes. Fix whatever breaks on the platform side first; you are on call for B and C.
- [ ] Tag `v0.1-day1`.
