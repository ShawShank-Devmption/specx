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

## Results

_Filled at the end of the build day by `make report` (`results/final/REPORT.md`). Table 7 (four-condition agent readiness) is pasted here._

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
