# SpecX — Complete Project Context for Coding Agents

> **Read this file fully before touching code.** Then read your dev file (`DEV_A_PLATFORM.md`, `DEV_B_SAFETY_ML.md`, `DEV_C_OPTIMISATION_EVAL.md`). The original research draft and work split live in `docs/reference/` for background; this file is the operational truth for the build.

**Compiled:** 2026-10-15 by the architect. **Build window:** one working day (12 h) with three devs each driving a coding agent. **Goal of the day:** a repo that runs end-to-end from a clean clone (`make demo`) and produces real, reproducible numbers for every claimed contribution (`results/final/REPORT.md`).

---

## 1. What SpecX is

WebMCP lets a web page expose JavaScript-backed tools (name, description, JSON input schema, handler) to AI agents, so an agent calls `add_to_cart({product_id, qty})` instead of scraping the DOM. Auto-generated tools are dangerous: they can invoke the wrong action, cause unapproved side effects, leak data through background requests, or be so badly described that agents cannot select them.

SpecX is a developer platform that:

1. **Generates** atomic WebMCP tools from a developer-authorised website using five evidence surfaces: repository code, rendered DOM, accessibility (ARIA) tree, network traces, and audit events. *(F3)*
2. **Verifies** every tool in a disposable browser sandbox against *executable* preconditions and postconditions derived from those surfaces, and **quarantines** anything unsafe, incorrect or unverifiable. *(F1)*
3. **Hardens** verification with two learned safety nets: a streaming anomaly detector over network + DOM-mutation streams *(S6)*, and an adversarial reinforcement-learning fuzzer rewarded for contract violations and race conditions *(S1)*.
4. **Predicts** risk before running anything, with a graph neural network over typed workflow graphs that recovers unmapped data dependencies and flags violation-prone execution paths *(S2)*.
5. **Optimises** the agent-facing metadata (names, descriptions, schemas — never the action) in a closed loop driven by a frozen evaluation agent, where a multimodal model turns failure bundles (DOM diff + network trace + screenshot) into *structured* patches *(F2 + S4)*, accepted only by a statistical regression gate that never trades safety for success.
6. **Measures** agent readiness across four conditions — raw DOM, generated, verified, optimised — on held-out tasks with paired trials and corrected significance tests. *(F4)*

**Thesis to demonstrate with numbers:** contract-verified, adversarially tested, learning-optimised WebMCP interfaces measurably improve agent success, efficiency and safety over raw DOM interaction and unverified generated tools, and each subsystem contributes an independently measurable share.

Closest prior art the paper must beat: ContractSkill (contracts for hand-drafted skills, page-state only), CoEvoSkills (LLM surrogate verifier, optimises skill code), FLORA (GNNs predicting workflow *performance*, not safety), WebRLED (RL for GUI coverage, not contract violations). Every design choice below exists to make those distinctions concrete and measurable.

---

## 2. Day-1 scope versus semester scope

We build the **whole architecture** today at demo scale, not a subset. Every stage must run and emit numbers. The table says where day-1 deliberately differs from the research draft so nobody over-builds and nobody silently skips.

| Area | Semester draft | **Day-1 build (what you implement today)** | Why |
|---|---|---|---|
| Seed apps | 3 apps, Dockerised, Postgres | **2 apps** (`shop`, `admin`), Express + **SQLite**, plain `node` processes. Third app (`blog`) only if Dev A is ahead at H8. | Zero infra friction; deterministic reset = copy `seed.db`. |
| Sandbox | Docker + mitmproxy | **Playwright Chromium in-process + CDP** network interception. Third-party requests blocked via `Fetch.failRequest`. No Docker. | Same observability, 10× faster to build. Docker-compose is an H12+ nicety. |
| Repo parsing | tree-sitter | tree-sitter for Express route extraction **if it installs cleanly in 15 min; else regex over `app.<verb>(`** (both are acceptable; record which in provenance). | Routes in our seed apps are trivially regular. |
| S6 | IF + LSTM-AE on live streams | **Exactly that**, trained on ~300 approved traces, evaluated on 4 injected leak kinds. | Lowest-risk feature; build it in full. |
| S1 | PPO/DQN, weeks of tuning | **PPO (SB3)** vs random vs coverage-greedy, **1 500 steps × 3 seeds × 2 apps**, 4 parallel sandbox sessions. | Enough to measure violations-per-1000-invocations honestly. |
| S2 | GCN/GAT, large label set | **GCN (PyG)**: link prediction on trace-confirmed data edges + path-risk classification on ~20 k verdicts; baselines rule-based + MLP. | Labels come from F1/S1 verdicts produced the same day. |
| S4 | LoRA-fine-tuned Qwen-VL/LLaVA | **Claude Opus 5.5 with vision + schema-constrained JSON output** as the multimodal structured patch generator. Three ablation arms run. Fine-tuning dataset is **exported** (`results/s4/dataset.jsonl`) for a later LoRA run. | A LoRA run is not a one-day task; the ablation (unstructured text → text-structured → multimodal-structured) is the claim, and it is measurable today. State this honestly in the report. |
| F4 trials | ≥ 10 paired trials, ≥ 3 apps | **5 paired trials** per (task, condition), 2 apps, 5 held-out tasks per app. Raise to 10 at H11 if the budget allows. | 200 episodes fit the day; stats engine handles any n. |
| Evaluation agent | frozen agent | **`claude-sonnet-5-5`**, `effort: medium`, frozen via `SPECX_AGENT_MODEL`. Generator / reviser / S4 use **`claude-opus-5-5`**. | ~800 episodes today; Sonnet keeps cost ≈ $50 and latency ≈ 30 s/episode. Model sampling is non-deterministic — this is a stated threat to validity, mitigated by paired seeds and n ≥ 5. |
| Delivery | CLI + CI + React dashboard | **All three**, minimal. Dashboard reads one JSON file. | Deliverables are part of the claim. |

Nothing else is cut. If you are behind, shrink *n* (trials, steps, seeds) — never drop a stage.

---

## 3. Architecture and data flow

```
                       ┌──────────────────────────── platform/ (TypeScript, Dev A) ────────────────────────────┐
                       │                                                                                        │
 seed-apps/shop ──┐    │  F3 generator ──► results/tools/<app>.tools.json ──┐                                   │
 seed-apps/admin ─┤    │   (code+DOM+ARIA+network+tests ─► atomic tools)    │                                   │
   (Express+SQLite│    │                                                    ▼                                   │
    + /__test/*)  │    │  F1 contract deriver ──► results/contracts/<app>.contracts.json                        │
                  │    │                                                    │                                   │
                  ▼    │  Sandbox HTTP :4000  ◄── PUT /sessions/{id}/tools ─┘                                   │
            Playwright │   sessions · reset · invoke · invoke_concurrent · replay · events · state · dom_action  │
            + CDP      │   ──► Verdict (clause results, effect diff, violations)  ──► results/verdicts/*.jsonl   │
                       │   ──► EventRecord stream (network/dom/storage/audit)      ──► results/events/*.jsonl    │
                       │                                                                                        │
                       │  Graph builder ──► results/graphs/<app>.graph.json (typed nodes, order/state/data edges)│
                       │  CLI: specx generate | verify | graph         CI: contracts · lint · unit tests         │
                       └──────────────────────────────────┬─────────────────────────────────────────────────────┘
                                                          │ HTTP + JSON validated against contracts/*.schema.json
        ┌─────────────────────────────────────────────────┴─────────────────────────────────────────────────────┐
        │ python/specx (Dev B + Dev C, one package, one venv)                                                   │
        │                                                                                                       │
        │  client/     SandboxClient · schemas.validate · results paths                      (Dev C, hour 1)    │
        │  safety/s6   feature windower ─► IsolationForest + LSTM-AE ─► verdict.anomaly      (Dev B)            │
        │  safety/s1   Gymnasium env over SandboxClient ─► PPO vs random vs coverage ─► s1 verdicts (Dev B)     │
        │  safety/s2   graph+verdicts ─► PyG GCN: link prediction + path-risk ─► gnn edges  (Dev B)             │
        │  evalx/      tasks · frozen agent harness (raw_dom | tools) ─► results/trials/*.jsonl (Dev C)         │
        │  optim/      F2 loop · failure bundles · reviser arms (text / structured / multimodal) · patch apply   │
        │              · regression gate                                                   (Dev C)              │
        │  stats/      paired tests · effect sizes · bootstrap CIs · Holm–Bonferroni ─► results/final/ (Dev C)  │
        └───────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                          │
                                           dashboard/ (React+Vite, Dev C) reads results/final/numbers.json
```

**Data dependency chain (why the build order is fixed):** seed apps → sandbox → tools+contracts → verdicts → (S6 needs approved traces) → (S1 needs sandbox + example args) → (S2 needs graph + S1/F1 verdicts) → (F2/S4 needs trials + bundles) → F4 needs verified + optimised tool sets → report.

---

## 4. Repository layout (fixed — do not invent new top-level directories)

```
specx/
├── README.md                     how to run; final numbers table pasted here at H12
├── Makefile                      every stage is a target; `make demo` runs the pipeline
├── .env.example                  copy to .env; never commit .env
├── .github/workflows/ci.yml      contracts + platform + python jobs; must be green to merge
├── .github/CODEOWNERS            contracts/ needs all three reviewers
├── contracts/                    ★ JSON Schemas + sandbox_api.md — the integration spec (read contracts/README.md)
├── fixtures/                     one valid instance of every schema; unblocks B and C before A's sandbox exists
├── docs/                         this file, dev files, reference/
├── scripts/check_contracts.py    validates fixtures/ and results/ against contracts/
├── platform/                     Dev A — TypeScript (Node 22+, ESM, strict TS)
│   ├── seed-apps/shop/           server.js, schema.sql, seed.db, leak.js, public/, app.json
│   ├── seed-apps/admin/          same shape
│   ├── scripts/start-apps.mjs    starts both apps
│   ├── src/contracts/            validate.ts (ajv), checkers.ts (one function per clause kind), derive.ts, args.ts
│   ├── src/generator/            repo.ts, dom.ts, network.ts, emit.ts, llm.ts (Opus 5.5 naming/descriptions)
│   ├── src/sandbox/              server.ts (HTTP), session.ts, observe.ts (CDP + MutationObserver), effects.ts
│   ├── src/graph/                build.ts, valueflow.ts, export.ts
│   ├── src/cli/main.ts           generate | verify | graph
│   └── tests/                    vitest; *.test.ts next to the unit they test
├── python/                       Dev B + Dev C — one package `specx`, managed with uv
│   ├── pyproject.toml            deps, ruff, pytest markers (sandbox, llm, slow)
│   ├── specx/client/             sandbox.py (SandboxClient), schemas.py (validate), paths.py (results dirs)
│   ├── specx/safety/s6/          features.py, models.py, train.py, score.py, inject.py, run.py
│   ├── specx/safety/s1/          env.py, mutations.py, baselines.py, train.py, run.py
│   ├── specx/safety/s2/          dataset.py, models.py, baselines.py, train.py, run.py
│   ├── specx/evalx/              tasks/<app>.tasks.json, agent.py, conditions.py, policy.py, run.py
│   ├── specx/optim/              bundles.py, reviser.py (3 arms), patch.py (apply), gate.py, loop.py
│   ├── specx/stats/              paired.py, report.py
│   └── tests/                    pytest; test_<module>.py; fixtures-driven, no network unless marked
├── dashboard/                    Dev C — Vite + React + TS; reads public/numbers.json
└── results/                      gitignored run outputs; results/final/ is committed at H12
    ├── tools/ contracts/ verdicts/ events/ graphs/ trials/ traces/ patches/ s6/ s1/ s2/ f2/ final/
```

**File practices**
- One responsibility per file; files ≤ ~400 lines. Split by *what changes together*, not by technical layer.
- Tests sit next to the thing they test (TS) or mirror the module path under `python/tests/` (Py).
- Every stage writes to `results/<stage>/` only, via `specx.client.paths` / `platform/src/paths.ts`. Never write elsewhere; never read another stage's *internal* files, only its published JSON.
- No notebooks in the repo. Exploration goes in `scratch/` (gitignored) and is deleted.

---

## 5. Integration contracts (the part that makes three parallel builds fit together)

Everything that crosses a dev boundary is one of nine JSON records, each with a schema in `contracts/`, a fixture in `fixtures/`, and a validator on both sides. **Read `contracts/README.md` and `contracts/sandbox_api.md` now.**

| Record | Schema | Producer → Consumers |
|---|---|---|
| App manifest | `app_manifest` | A → A, C |
| Tool definition | `tool_definition` | A (F3) → B, C; **C revises `name/description/input_schema` only** |
| Tool contract | `contract` | A → A |
| Event record | `event_record` | A → B (S6, S1), C (S4) |
| Verdict | `verdict` | A → B (S1 reward, S2 label), C (gate); **B fills `anomaly`** |
| Workflow graph | `workflow_graph` | A → B (S2), C (F4); **B appends `evidence:"gnn"` edges** |
| Eval task | `task` | C → C |
| Trial result | `trial_result` | C → C, B (ablation stats) |
| Tool patch | `patch` | C → C |

Rules:
1. **Additive-only schema changes**, by PR titled `contracts: …`, reviewed by all three. Never rename/remove a field another dev consumes.
2. Validate on write **and** on read. TS: `validate(name, obj)` in `platform/src/contracts/validate.ts`. Py: `specx.client.schemas.validate(name, obj)`. Both raise with the JSON-pointer path.
3. The fixtures are the executable spec. If your code cannot consume a fixture, your code is wrong, not the fixture.
4. `scripts/check_contracts.py` also validates everything in `results/`; `make report` runs it first.

---

## 6. Runtime topology

| Process | Port | Started by | Needed by |
|---|---|---|---|
| `shop` seed app | 5101 | `make apps` | sandbox, raw_dom harness (via sandbox) |
| `admin` seed app | 5102 | `make apps` | same |
| sandbox HTTP server | 4000 | `make sandbox` | every Python stage |
| dashboard (Vite) | 5173 | `make dashboard` | humans |

Environment (`.env`, read by both sides): `ANTHROPIC_API_KEY`, `SPECX_AGENT_MODEL=claude-sonnet-5-5`, `SPECX_GEN_MODEL=claude-opus-5-5`, `SPECX_SANDBOX_URL=http://127.0.0.1:4000`, `SPECX_RESULTS_DIR=results`.

---

## 7. Seed applications (Dev A builds; everyone depends on these exact names)

Both are Express 4 + `better-sqlite3`, server-rendered HTML + a little vanilla JS, cookie session auth, and the **test hooks** in `contracts/sandbox_api.md` (`/__test/reset|db|audit|leak|apply`). Every state-changing endpoint writes an `audit_log` row (`event, actor, entity, entity_id, ts`). Every interactive element has a `data-testid` **and** a proper ARIA role/name (tools cite both as provenance).

### `shop` (:5101) — e-commerce
Tables: `products(id,name,price_cents,stock)`, `users(id,username,password,address)`, `cart_items(id,user_id,product_id,qty)`, `orders(id,user_id,total_cents,status,created_at)`, `order_items(id,order_id,product_id,qty,price_cents)`, `audit_log`.
Seed: products 1 Blue Mug 1299 · 2 Red Notebook 499 · 3 Green Pen 199 · 4 Black Lamp 2599 · 5 White Chair 7999; user `alice/alice123` (id 1) with a saved address.
Pages: `/login`, `/products`, `/products/:id`, `/cart`, `/orders`.
API: `GET /api/products`, `GET /api/products/:id` (returns `id` — **deliberately not `product_id`**, so name-matching dependency rules miss it and value-flow tracing / S2 must recover it), `GET /api/cart`, `POST /api/cart {product_id,qty}`, `DELETE /api/cart/:product_id`, `POST /api/orders {confirm}`, `GET /api/orders`, `POST /api/login`.
**Intentional defects (S1 must find them; do not fix them):**
- **Race:** `POST /api/orders` reads the cart, inserts the order, then deletes the cart with no transaction — two concurrent calls create **two orders**. Contract invariant `inv_at_most_once(orders)` catches it only under `invoke_concurrent`.
- **Boundary:** `POST /api/cart` with `qty > stock` succeeds and drives stock negative (no check). Postcondition `db_delta(products.updated=1)` with `stock >= 0` row check fails.
- **Unapproved endpoint:** `POST /api/analytics` exists, is not in the manifest, and fires only in leak mode.
Expected generated tools (7): `list_products, get_product, view_cart, add_to_cart, remove_from_cart, place_order, list_orders`.

### `admin` (:5102) — CRUD/admin
Tables: `users(id,username,email,role in {viewer,editor,admin},active)`, `notes(id,user_id,body)`, `audit_log`.
Seed: 6 users incl. `root/root123` (id 1, role admin), 10 notes.
Pages: `/login`, `/users`, `/users/:id`, `/users/new`.
API: `GET /api/users`, `GET /api/users/:id`, `POST /api/users`, `PATCH /api/users/:id {username?,email?,active?}`, `POST /api/users/:id/role {role}`, `DELETE /api/users/:id`, `POST /api/login`.
**Intentional defects:**
- **Hidden side effect:** `DELETE /api/users/:id` silently deletes the user's `notes` rows; the contract for `delete_user` expects `db_delta(notes.deleted=0)`.
- **State-dependent invariant:** `PATCH /api/users/1 {active:false}` deactivates the only admin; invariant `db_row_exists(users, {role:"admin", active:1})` fails. Only reachable through a specific sequence — this is what S2's path-risk head should learn.
- **Missing audit:** `POST /api/users/:id/role` does **not** write an audit row (contract `audit_event("user.role")` fails).
Expected generated tools (7): `list_users, get_user, create_user, update_user, set_role, deactivate_user, delete_user`.

**Leak mode** (`POST /__test/leak {kind, delay_ms}`): arms a one-shot leak that fires after the next state-changing call, in the page's `phase:"post"` window: `delayed_post` (POST /api/analytics), `storage_write` (`localStorage.__trk`), `third_party_fetch` (`https://tracker.example.invalid`), `background_poll` (`setInterval` GET /api/cart or /api/users every `delay_ms`).

---

## 8. Pipeline stages and what each must publish

| `make` target | Owner | Reads | Writes | Done when |
|---|---|---|---|---|
| `generate` | A | seed-app code, live DOM/ARIA, recorded network | `results/tools/<app>.tools.json`, `results/contracts/<app>.contracts.json` | 7 tools per app, each with ≥ 2 provenance surfaces and a contract with ≥ 1 postcondition; all validate |
| `verify` | A (+B score) | tools, contracts | `results/verdicts/f1.jsonl`; tool `status` set; `anomaly` filled by `specx.safety.s6.score` | every tool run 3× single + 1 replay + (write/delete/payment) 1 concurrent×2; replay deterministic; quarantine reasons machine-readable |
| `graph` | A | tools, contracts, verdicts | `results/graphs/<app>.graph.json` | order edges from traces, state edges from contracts, data edges from value-flow (evidence `trace`) and name match (evidence `rule`) |
| `s6` | B | events (approved runs + injected leaks) | `results/s6/metrics.json`, `results/s6/model.*` | detection rate per leak kind and FPR on benign, for IF / LSTM-AE / both |
| `s1` | B | sandbox, tools, example_args | `results/verdicts/s1.jsonl`, `s1_random.jsonl`, `s1_coverage.jsonl`, `results/s1/metrics.json` | unique violation signatures per 1 000 invokes and time-to-first-violation, 3 seeds × 2 apps × 3 methods |
| `s2` | B | graphs, all verdicts | `results/s2/metrics.json`; `evidence:"gnn"` edges merged into graphs | link-prediction AUC/P/R and path-risk AUC/P/R/F1 for GCN vs rule-based vs MLP on a session-disjoint held-out split |
| `baseline` | C | tasks, sandbox | `results/trials/raw_dom.jsonl`, `generated.jsonl`, `results/traces/*.json` | 5 held-out tasks × 2 apps × 5 seeds per condition |
| `optimise` | C | train tasks, failing traces, tools | `results/patches/*.patch.json`, `results/trials/gate_<arm>_<iter>.jsonl`, `results/tools/<app>.optimised.<arm>.tools.json`, `results/f2/metrics.json`, `results/s4/dataset.jsonl` | success per iteration and iterations-to-convergence for the 3 arms; accepted/rejected log with gate statistics |
| `evaluate` | C | held-out tasks, verified + optimised tool sets | `results/trials/verified.jsonl`, `optimised.jsonl` | same 5 × 2 × 5 design |
| `report` | C | everything in `results/` | `results/final/numbers.json`, `results/final/REPORT.md`, `dashboard/public/numbers.json` | the seven tables in §9 with CIs and corrected p-values |

---

## 9. Experiment design and the numbers we must produce

Conditions: **raw_dom → generated (F3) → verified (F1+S6+S1 quarantine) → optimised (F2+S4)**, same frozen agent, same held-out tasks, same seeds (trial *k* of task *T* uses seed *k* in every condition → paired).

Metrics per trial: `success`, `steps`, `input_tokens + output_tokens`, `policy_violations` (Completion-under-Policy style), `quarantined_tool_calls`, `unapproved_calls`.

Statistics (`specx.stats.paired`): success → exact McNemar on paired outcomes + Cohen's *h*; steps/tokens → Wilcoxon signed-rank + Cohen's *d*; 95 % bootstrap CIs (2 000 resamples); **Holm–Bonferroni** across each family of comparisons; report *n* everywhere. The F2 gate reuses the same functions.

**The seven result tables** (`results/final/REPORT.md`; the dashboard renders the same JSON):

1. **Generation** — per app: tools generated, provenance surfaces per tool (mean), tools with ≥ 3 surfaces.
2. **Verification** — per app: verified / quarantined / unverifiable, quarantine reasons by category, replay-determinism rate.
3. **S6** — per leak kind: detection rate for IF-only, LSTM-AE-only, combined; false-positive rate on benign runs; threshold used.
4. **S1** — per method (random, coverage-greedy, PPO): unique violation signatures per 1 000 invokes (mean ± sd over 3 seeds), time-to-first-high-severity violation, severity mix; per app.
5. **S2** — link prediction (AUC, P, R @0.5) and path-risk (AUC, P, R, F1) for rule-based, MLP, GCN; number of trace-confirmed edges the rule-based checker missed that GCN recovered.
6. **F2/S4** — per arm: success rate on train tasks per iteration, iterations-to-convergence, patches proposed/accepted/rejected, rejection reasons (no improvement vs safety regression).
7. **F4 readiness** — 4 conditions × (success %, mean steps, mean tokens, policy-violation rate, unapproved calls) with 95 % CIs and Holm-corrected p-values vs the previous condition.

A table with *n* = 0 or a missing arm is a **failed deliverable**, not an acceptable gap.

---

## 10. LLM usage rules (both sides)

- SDKs only: `@anthropic-ai/sdk` (TS), `anthropic` (Py). No raw HTTP, no other providers.
- Models: generation/revision/S4 → `claude-opus-5-5`; frozen evaluation agent → `claude-sonnet-5-5`. Read them from env, never hard-code. Do not append date suffixes.
- Thinking is on by default on both; control cost with `output_config.effort` (`"medium"` for the agent, `"high"` for the generator/reviser). Do **not** send `budget_tokens` or `thinking: {type:"disabled"}` (400 on these models). No non-default `temperature`.
- **Forced tool choice (`tool_choice: any|tool`) is rejected** on these models. Use `auto` + an explicit instruction, `strict: true` on every tool, and `output_config.format` (JSON Schema) whenever you need JSON back. Python: `client.messages.parse(..., output_format=PydanticModel)` → `response.parsed_output`.
- Always check `stop_reason` before reading content; handle `refusal` and `max_tokens`. Parse tool inputs with `json.loads`/`JSON.parse`; never string-match.
- Put the stable system prompt and tool list first and mark them `cache_control: {type:"ephemeral"}`; put the per-step observation last. Log `usage` on every call into the trial record.
- Mark every test that calls the API with `@pytest.mark.llm`; CI never runs them. Budget for the day ≈ $60; the harness must print cumulative spend every 50 episodes.

---

## 11. Code quality standard (non-negotiable; CI enforces the mechanical parts)

**TypeScript (platform/)** — ESM, `strict`, `noUncheckedIndexedAccess`; no `any` (use `unknown` + narrowing or zod); zod schemas for every HTTP body; `vitest` unit tests for every pure module (checkers, derive, args, graph) and one integration test per sandbox endpoint behind `SANDBOX_INTEGRATION=1`; structured logs via a tiny `log.ts` (`JSON.stringify({ts, level, mod, msg, ...})` to stderr), never `console.log` in library code; every file starts with a 2–4 line doc comment saying what it owns.

**Python (python/)** — 3.11, `ruff` (lint + format), type hints everywhere, `pydantic` models for every record you construct, `pathlib` only, `typer` CLIs with `--out` and `--seed`; `pytest` with markers `sandbox` / `llm` / `slow`; numpy/torch seeds set from `--seed` in one `specx.client.seeding.seed_everything(seed)`; every `run.py` writes `metrics.json` **and** a `run.json` with git SHA, args, timestamps, model ids.

**Both** — small pure functions, I/O at the edges; no global mutable state; fail loudly (raise) on invalid records; comments explain *why*, not what; no TODOs left in merged code (open an issue instead); no dead code; no copy-pasting a sibling's helper — import it (B and C share `specx.client` and `specx.stats`).

**Tests** — write the failing test first for anything with logic. Unit tests must run offline in < 60 s total per side. Integration tests use fixtures as inputs and assert on schema-valid outputs. Determinism tests exist for: sandbox replay, seeded S1 random baseline, seeded S6 training, seeded trial ordering.

---

## 12. Git workflow (main contains only integrated, CI-green code)

- `main` is protected: no direct pushes, no force pushes, PRs only, CI must pass, **one approval** from another dev (contracts/ changes: two).
- Branch names: `dev-a/<task-id>-<slug>`, e.g. `dev-a/A4-sandbox-invoke`, `dev-b/B2-s6-models`, `dev-c/C3-f2-loop`. One branch per task id from your dev file.
- Commit early and often with **Conventional Commits**: `feat(sandbox): invoke endpoint with effect diff`, `fix(s6): window alignment at tool_end`, `test(stats): mcnemar edge cases`, `contracts: add verdict.sequence_prefix`, `docs: …`. Every commit must pass `make test` locally.
- Rebase on `main` before opening a PR (`git fetch && git rebase origin/main`); **squash-merge** PRs; delete branches after merge.
- PR template (in the description): *What* · *How to run* · *Numbers produced (paste)* · *Schema changes (none / list)* · *Risks*.
- Integration gates (§13) are merge deadlines: at each gate, whatever is on `main` is what the next stage builds against. Do not block a gate on polish — merge the working subset and open a follow-up branch.
- `results/` is gitignored except `results/final/`, committed once at H12 together with the README numbers table. Model checkpoints (`*.pt`, `*.zip`) are never committed; `run.py` must retrain in < 10 min.
- Tag `v0.1-day1` on `main` when `make demo` passes from a clean clone.

---

## 13. Timeline and integration gates (H0 = kickoff)

| Hour | Dev A — Platform | Dev B — Safety ML | Dev C — Optimisation & Eval |
|---|---|---|---|
| **H0–1** | A0 setup, A1 `shop` app + test hooks | B0 setup, B1 windower on fixture events | C0 setup, **C1 `specx.client`** (SandboxClient, schemas, paths, seeding) → merged by H1 |
| **H1–2** | A1 `admin` app; A2 contract validate + checkers | B2 S6 models + training on synthetic-from-fixture traces (unit-tested) | C2 stats engine; C3 tasks (10 per app) |
| **H2–3** | A3 sandbox: sessions, reset, invoke, events, state | B3 S1 env + mutations against `FakeSandbox`; random baseline | C4 agent harness (raw_dom + tools modes) against `FakeSandbox` |
| **H3 — GATE 1** | `make sandbox` up; replay determinism test green on fixture tools | switch to real sandbox | switch to real sandbox |
| **H3–5** | A4 F3 generator both apps; A5 F1 deriver; `verify` CLI | B4 record ~300 approved traces, train S6, run leak injections → table 3 | C5 raw_dom baseline trials (table 7, col 1) |
| **H5 — GATE 2** | `results/tools`, `results/contracts`, `results/verdicts/f1.jsonl` for both apps; statuses set | | |
| **H5–8** | A6 graph builder + value-flow; `example_args`; 8 parallel sessions; `invoke_concurrent` | B5 S1 on real sandbox: random, coverage, PPO × 3 seeds → table 4 | C6 generated-condition trials; C7 F2 loop (text_trace arm) + gate; bundle harvesting |
| **H8 — GATE 3** | graphs for both apps; S1 verdicts on `main` | | |
| **H8–10** | A7 CLI polish, CI green, README run section, (A8 `blog` app only if ahead) | B6 S2 dataset + GCN + baselines → table 5; merge gnn edges | C8 S4 arms (text_structured, multimodal_structured) → table 6; C9 verified + optimised trials → table 7 |
| **H10–12** | all: `make demo` from clean clone, `make report`, dashboard, README numbers, tag `v0.1-day1` | B7 ablation write-up + threats to validity | C10 dashboard; `report` |

**Decision rules at gates:** if the sandbox is not up at H3, B and C keep going on `FakeSandbox` + fixtures and A drops `admin` to a stub (one tool) until shop is solid. If S1-PPO does not beat random at H8 after 2 runs, keep the numbers as they are (an honest negative is a result) and reallocate B to S2. If the API budget is exhausted, cut trials to *n*=3 and say so in the report.

---

## 14. Ownership, communication, red team

- **Dev A** owns everything a tool *is* and *does*: seed apps, generation, contracts, sandbox, graph, CLI, CI. If a record is wrong, A's validator should have caught it.
- **Dev B** owns the three learned safety components and their ablations. B never edits `platform/`; B asks A for endpoints through `contracts/` PRs.
- **Dev C** owns the frozen agent, the loop, the gate, the benchmark, the stats, the dashboard, and `specx.client` (because B and C both use it and C needs it first).
- Questions go in the shared channel with the schema name and the fixture that reproduces the issue. Decisions get recorded as a one-line entry in `docs/DECISIONS.md` (create it on first use).
- Red-team rotation at H10: A attacks B's numbers (leakage between train/held-out sessions? reward hacking?), B attacks C's (are policy violations mechanical? are seeds paired?), C attacks A's (is replay really deterministic? are quarantine reasons machine-readable?).

---

## 15. Glossary (the exact words we use in code and docs)

**Atomic tool** — one verifiable action per tool. **Contract** — executable pre/postconditions + invariants. **Clause** — one checkable condition (`kind` + `params`). **Verdict** — result of one sandbox invoke. **Violation signature** — stable dedup key of a failed clause; S1's unit of reward. **Effect diff** — db/network/dom/storage/audit deltas of a run. **Quarantine** — tool excluded from the shipped set with machine-readable reasons. **Approved endpoint** — in the app manifest. **Third-party** — host not in `approved_hosts`. **Leak** — unapproved effect in the post phase. **Condition** — one of raw_dom / generated / verified / optimised. **Paired trial** — same task, same seed, different condition. **Revision** — a `metadata_revision` bump via an accepted patch. **Gate** — the statistical + safety acceptance test for a revision. **Arm** — one S4 ablation modality. **Path risk** — probability that invoking tool *t* after prefix *p* violates a clause.

---

## 16. Reading list (10 minutes, in this order)

1. `contracts/README.md` and `contracts/sandbox_api.md`
2. the fixture for every schema you produce or consume (`fixtures/`)
3. your dev file in `docs/`
4. `docs/reference/SpecX_Full_Context.md` §3.5 (the four novelty claims) — so your implementation matches the claim it supports
