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
- 2026-10-15 · A · New `specx quarantine` step after `make s1`: folds high-severity, non-precondition violations from S1 sources plus S6 anomaly flags on a majority of a tool's own F1 runs. `s6_inject` is refused (its leaks are injected by the harness, not caused by tools).
- 2026-10-15 · A · Generator names tools with a deterministic template namer (accessible name of the triggering button, else verb + resource). `--namer llm` uses Claude Opus 5.5 when `ANTHROPIC_API_KEY` is set.
- 2026-10-15 · A · Dropped `exactOptionalPropertyTypes` from the platform tsconfig — friction with Playwright and zod types without a safety gain for this codebase.
- 2026-10-15 · A · `make demo` order is generate → verify → s6 → s1 → quarantine → graph → s2 …: value-flow and order edges come from S1 and agent traces (F1 resets between tools), so the graph is built after S1. S6 scoring of F1 verdicts moved from `make verify` to `make s6`.
- 2026-10-15 · A · Verification rule: a tool is verified only if every single run on valid example arguments passes and its replay is identical; any non-precondition violation of any severity quarantines it (the missing role audit is medium severity). Concurrent runs count only for violations, not handler errors (a second idempotent delete returning 404 is fine).
- 2026-10-15 · A · Value-flow data edges match only id-like fields within one reset epoch **and** only when the field is semantically compatible with the parameter (same name, or a bare `id` from a tool whose resource matches `<x>_id`). Seed ids are small integers shared across id spaces, so value equality alone links unrelated tools.
- 2026-10-15 · A · A8 (third seed app `blog`) skipped for day 1; two apps cover all four defect classes.
- 2026-10-15 · A · Crawler reads API responses inside a `page.route` before handing them back, so bodies survive the reload/navigation the UI does after a create or delete; fill values are unique per field to avoid UNIQUE collisions.
- 2026-10-15 · A · Raw-DOM actions are recorded as their own runs (`<session>_a<n>`) so the raw_dom condition's network effects (policy violations, unapproved calls) are observable.
