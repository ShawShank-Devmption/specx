# SpecX

**Verified Website-to-WebMCP Conversion, Sandboxed Agent Testing and Safety-Preserving Optimisation.**
AI course project · VIT (SCOPE) · Guide: Dr. Yoganand S (CFAIR).

SpecX turns a developer-authorised website into atomic WebMCP tools, verifies each tool against executable contracts in a disposable browser sandbox, hardens verification with a streaming anomaly detector (S6) and an adversarial RL fuzzer (S1), predicts risky paths with a GNN over typed workflow graphs (S2), optimises tool metadata in a safety-gated closed loop with multimodal structured patches (F2 + S4), and measures agent readiness across four conditions (F4).

## Start here

| If you are… | Read |
|---|---|
| Any coding agent or dev | [`docs/00_PROJECT_CONTEXT.md`](docs/00_PROJECT_CONTEXT.md) — the complete context, architecture, rules, timeline |
| Dev A (platform: seed apps, generator, contracts, sandbox, graph, CLI/CI) | [`docs/DEV_A_PLATFORM.md`](docs/DEV_A_PLATFORM.md) |
| Dev B (safety ML: S6 → S1 → S2) | [`docs/DEV_B_SAFETY_ML.md`](docs/DEV_B_SAFETY_ML.md) |
| Dev C (optimisation & evaluation: client, stats, agent, F2/S4, F4, dashboard) | [`docs/DEV_C_OPTIMISATION_EVAL.md`](docs/DEV_C_OPTIMISATION_EVAL.md) |
| Integrating anything | [`contracts/README.md`](contracts/README.md) and [`contracts/sandbox_api.md`](contracts/sandbox_api.md) |
| Running without paid API calls | [`docs/FREE_INTEGRATION.md`](docs/FREE_INTEGRATION.md) — measured integration checks and remaining work |

Background: `docs/reference/` (research draft PDF, work split PDF, full research context).

## Run it

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY (needed by the Python stages and --namer llm)
make setup                      # node deps + playwright chromium + python venv (uv)
make test                       # contracts + unit tests, offline
cd platform && npm run test:integration   # sandbox + generator against real Chromium (~2 min)
```

One command (starts apps + sandbox, runs the target, stops everything):

```bash
scripts/run_all.sh platform-demo   # Dev A stages: generate -> verify -> graph
scripts/run_all.sh                 # full pipeline: make demo
```

Or by hand, in three terminals:

```bash
make apps                       # shop :5101, admin :5102
make sandbox                    # sandbox HTTP API :4000 (contracts/sandbox_api.md)
make demo                       # generate → verify → s6 → s1 → quarantine → graph → s2 → baseline → optimise → evaluate → report
make dashboard                  # :5173, renders results/final/numbers.json
```

Individual stages: `make help`. Platform CLI: `cd platform && npm run cli -- help`.

What the platform stages produce today (template namer, 3 runs per tool):

| App | Tools | Verified | Quarantined (reason) | Replay deterministic |
|---|---|---|---|---|
| shop | 7 | 6 | `place_order` (checkout race under concurrent calls) | 7/7 |
| admin | 7 | 5 | `set_role` (no audit row), `delete_user` (hidden cascade deletes notes) | 7/7 |

## Connect your Claude agent to the verified tools

Only tools that passed contract verification are exposed; quarantined tools are refused with the reason. Every call runs in a sandbox session, so contracts still apply, and the reply carries the output plus `SpecX contract check: pass|fail`.

**Prerequisites:** `make apps` running, and `make generate verify` done. Add `make s1 quarantine` to drop tools that fuzzing broke.

**MCP (Claude Code, Claude Desktop, any MCP client).** Opening Claude Code in this repo offers `specx-shop` and `specx-admin` from `.mcp.json`; approve them once. To register them elsewhere:

```bash
claude mcp add specx-shop -- "$PWD/platform/node_modules/.bin/tsx" "$PWD/platform/src/mcp/server.ts" --app shop
claude mcp add specx-admin -- "$PWD/platform/node_modules/.bin/tsx" "$PWD/platform/src/mcp/server.ts" --app admin
```

For Claude Desktop, add the same command and arguments, as absolute paths, under `mcpServers` in its config file.

**WebMCP (agents that browse the site), the project's real output.** `make generate` also writes a WebMCP-native tool set; `make webmcp` verifies it in the sandbox and exports the verified tools as `results/webmcp/<app>.webmcp.js`, which each app serves at `/webmcp.js`.
- Write actions are `ui` tools: they fill the page's own fields and click its own button, so the app's code runs and the page updates in front of the user. They return what the server answered.
- Each tool is registered only on its page: `add_to_cart` on `/products/:id` (the product comes from the page; the agent only gives `qty`), `remove_from_cart` on `/cart`. Reads are available on every page.
- Payment and delete tools show an in-page dialog and run only after the user clicks **Allow**. The WebMCP draft has no confirmation API, so the site asks.
- Quarantined tools are never exported.

### How to test the WebMCP tools

1. **Automated, real browser (about 2 minutes):** generates from a live crawl, verifies in the sandbox, exports, then uses the tools in the page through a stand-in WebMCP host.

   ```bash
   cd platform && SANDBOX_INTEGRATION=1 npx vitest run tests/webmcp-ui.integration.test.ts
   ```

2. **By hand, any Chrome, no flag:** with `make apps` running and `make generate webmcp` done, open http://127.0.0.1:5101, log in as `alice` / `alice123`, open a product page and run in the DevTools console:

   ```js
   __specxWebMCPTools.map(t => t.name)                                    // tools for this page
   await __specxWebMCPTools.find(t => t.name === "add_to_cart").execute({ qty: 2 })
   ```

   The page shows "Added to cart". On `/cart`, `remove_from_cart` asks you to Allow or Deny first.

3. **As a real browser agent sees it:** in Chrome 146+, enable `chrome://flags/#enable-webmcp-testing`, relaunch, then install Google's Model Context Tool Inspector extension. Open the shop: the inspector lists the tools registered on each page and lets you call them.

## Results

The C10 reporter and dashboard are implemented. Real-browser template generation and F1 verification now populate Tables 1–2: Shop has 6 verified / 1 quarantined tool, Admin has 5 verified / 2 quarantined, and replay checks pass 7/7 per app. Model-driven benchmark outputs and B's full safety-stage metrics are not yet available; `make report` generates an **incomplete** report and exits **2**. `MISSING` is unknown, not a measured zero. See the [no-paid-API checkpoint](docs/FREE_INTEGRATION.md) for scope and reproducible commands.

Table 7 — four-condition held-out readiness (current generated report; no live observations):

| app | condition | n | success % [95% CI] | steps [95% CI] | tokens [95% CI] | policy % [95% CI] | unapproved calls | quarantined calls |
|:---|:---|---:|:---|:---|:---|:---|:---|:---|
| shop | raw_dom | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| admin | raw_dom | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| shop | generated | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| admin | generated | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| shop | verified | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| admin | verified | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| shop | optimised | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |
| admin | optimised | 0 | MISSING | MISSING | MISSING | MISSING | unknown | unknown |

Run `make report` after the upstream experiments to regenerate [REPORT.md](results/final/REPORT.md) and [numbers.json](results/final/numbers.json). The reporter copies the same JSON to `dashboard/public/numbers.json`; `cd dashboard && npm ci && npm run dev` opens the dashboard at `http://127.0.0.1:5173`. Update this table from the generated Table 7 when live results exist. See [dashboard instructions](dashboard/README.md).

## Layout

```
contracts/   JSON Schemas + sandbox HTTP API — the integration spec (additive changes only, 3 reviewers)
fixtures/    one valid instance of every schema; CI validates them
platform/    Dev A — TypeScript: seed apps, F3 generator, F1 contracts, sandbox, graph builder, CLI
python/      Dev B + Dev C — one package `specx`: client, safety (s6/s1/s2), evalx, optim, stats
dashboard/   Dev C — React + Vite, reads results/final/numbers.json
results/     run outputs (gitignored except results/final/)
docs/        context + dev plans + reference material
```

## Git

`main` is integration-only and protected (PR + CI + one review; two for `contracts/`). Branches `dev-{a,b,c}/<task-id>-<slug>`, Conventional Commits, rebase then squash-merge. Full rules in `docs/00_PROJECT_CONTEXT.md` §12.
