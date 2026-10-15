# Decisions

One line per decision that deviates from or sharpens the plan. Newest last.

- 2026-10-15 · A · `node:sqlite` (built into Node ≥ 22.13) instead of `better-sqlite3` — no native build on Node 26, one fewer dependency.
- 2026-10-15 · A · Regex route parser instead of tree-sitter — seed-app routes are regular; tree-sitter has no prebuilt binaries for Node 26. Provenance records `parser: regex`.
- 2026-10-15 · A · Express 5 instead of 4 — matches `@types/express` 5; routes only use `:param` segments.
- 2026-10-15 · A · Seed apps are multi-tenant: one in-memory SQLite DB per sandbox session (`specx_tenant` cookie / `x-specx-tenant` header). Needed for ≥ 8 parallel sessions without cross-talk.
- 2026-10-15 · A · Sandbox observes through Playwright request/response events and aborts third-party hosts with `context.route`, rather than raw CDP `Fetch` — same data, less code. DOM mutations and storage writes come from an init script.
- 2026-10-15 · A · Business invariants (`inv_stock_nonnegative`, `inv_active_admin`) are declared in each app manifest instead of being inferred from column names. Clause kind `db_no_row` added.
- 2026-10-15 · A · Concurrent invokes evaluate preconditions + invariants only, one page per call. `inv_at_most_once` is attached to `payment` tools only.
- 2026-10-15 · A · Admin deactivation is its own route (`POST /api/users/:id/deactivate`) so one route maps to one atomic tool.
- 2026-10-15 · A · New `specx quarantine` step folds S1/S6 high-severity violations into tool status after `make s1`, so the verified condition reflects F1 + S6 + S1.
- 2026-10-15 · A · Generator names tools with a deterministic template namer (accessible name of the triggering button, else verb + resource). `--namer llm` uses Claude Opus 5.5 when `ANTHROPIC_API_KEY` is set.
- 2026-10-15 · A · Dropped `exactOptionalPropertyTypes` from the platform tsconfig — friction with Playwright and zod types without a safety gain for this codebase.
