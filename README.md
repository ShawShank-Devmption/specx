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
cp .env.example .env            # add ANTHROPIC_API_KEY
make setup                      # node deps + playwright chromium + python venv (uv)
make test                       # contracts + unit tests, offline

# three terminals (or scripts/run_all.sh)
make apps                       # shop :5101, admin :5102
make sandbox                    # :4000
make demo                       # generate → verify → graph → s6 → s1 → s2 → baseline → optimise → evaluate → report
make dashboard                  # :5173, renders results/final/numbers.json
```

Individual stages: `make generate verify graph s6 s1 s2 baseline optimise evaluate report` (see `make help`).

## Results

The C10 reporter and dashboard are implemented. Live experiment outputs are not yet available; `make report` currently generates an **incomplete** report and exits **2**. `MISSING` is unknown, not a measured zero.

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
