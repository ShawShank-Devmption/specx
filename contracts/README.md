# `contracts/` — the single source of truth for every record that crosses a dev boundary

**Rule 0:** nothing crosses between `platform/` (TS) and `python/` (Py) except (a) the HTTP API in `sandbox_api.md` and (b) JSON files that validate against a schema in this directory. If you need a field that is not here, add it to the schema **first**, in a PR titled `contracts: …`, and ping the other two devs. Additive changes only (new optional fields); never rename or remove a field once another dev has consumed it.

| Schema | Producer | Consumers | File location at runtime |
|---|---|---|---|
| `app_manifest.schema.json` | A | A (sandbox), C (harness) | `platform/seed-apps/<app>/app.json` |
| `tool_definition.schema.json` | A (F3) · revised by C (F2/S4) | B (S1 action space, S2 nodes), C (agent tools) | `results/tools/<app>.tools.json` (array) |
| `contract.schema.json` | A (F1) | A (sandbox checkers) | `results/contracts/<app>.contracts.json` (array) |
| `event_record.schema.json` | A (sandbox) | B (S6 windower, S1 obs), C (S4 bundles) | `results/events/<session>.jsonl` and `GET /sessions/{id}/events` |
| `verdict.schema.json` | A (sandbox) · `anomaly` filled by B (S6) | B (S1 reward, S2 labels), C (gate safety invariants, dashboard) | `results/verdicts/<source>.jsonl` |
| `workflow_graph.schema.json` | A (graph builder) · `evidence:gnn` edges added by B | B (S2), C (F4 manifest, dashboard) | `results/graphs/<app>.graph.json` |
| `task.schema.json` | C | C (harness) | `python/specx/evalx/tasks/<app>.tasks.json` (array) |
| `trial_result.schema.json` | C (harness) | C (stats, gate), B (ablation stats) | `results/trials/<condition>.jsonl` |
| `patch.schema.json` | C (F2 reviser / S4) | C (apply), dashboard | `results/patches/<revision>.json` |

Validation helpers (both sides must use them — never hand-roll):
- TS: `platform/src/contracts/validate.ts` → `validate("verdict", obj)` using **ajv** (draft 2020-12). Throws with the JSON-pointer path.
- Py: `specx.client.schemas.validate("verdict", obj)` using **jsonschema** `Draft202012Validator`. Same name keys as the filenames minus `.schema.json`.

`fixtures/` holds one valid instance of each schema. CI (`make check-contracts`) validates every fixture against its schema on every PR, so a schema change that breaks a fixture fails CI before it breaks a teammate.

## Compound task success

`task.success_check` remains required and unchanged. Tasks may additionally provide
a non-empty `success_checks` array of objects with the same shape. The primary
check **and every additional check** must pass against one final state snapshot.
Omitting the array preserves the original single-check behavior. See
`fixtures/tasks/admin.compound.tasks.json` for the two-goal example; its existing
`setup.users` inserts dana after reset, independently of training episodes.

This optional field is an additive shared-contract change and must be reviewed in
a `contracts: …` PR before integration. No HTTP API change is required for setup.

## Clause kinds and their `params` (implemented by the sandbox checker, Dev A)

**Value references** inside `params` (resolved by the sandbox per run): `"$args.<name>"` → the invoke argument; `"$user.id"` → id of the logged-in manifest user (looked up in the `users` table by `auth.username`).

**`where` syntax** (used by `db_row_exists`, `db_no_row`, manifest invariants): `{column: value}` with `value` either a scalar / value reference (equality, compared as strings so `1` equals `"1"`, matching SQLite affinity) or `{"op": "<"|"<="|">"|">="|"!=", "value": number|string}`.

**Counters** in `db_delta` are either an exact integer or `{"min": n, "max": n}` (either bound optional). Omitted counters are not checked.

| kind | surface | params | passes when |
|---|---|---|---|
| `dom_exists` | dom | `{selector}` | `page.locator(selector).count() > 0` |
| `dom_absent` | dom | `{selector}` | count == 0 |
| `dom_text_contains` | dom | `{selector, text}` | inner text of selector contains `text` (case-insensitive) |
| `url_matches` | dom | `{pattern}` (regex) | `page.url()` matches |
| `auth_state` | aria | `{logged_in: bool}` | `[data-testid=user-menu]` present (logged in) / absent |
| `network_calls` | network | `{method, path, min?, max?}` | first-party requests of this run (during + post) matching `method` and the `path` pattern number within `[min,max]` (default exactly 1) |
| `no_unapproved_endpoint` | network | `{}` | zero first-party fetch/xhr requests with `approved=false` |
| `no_third_party` | network | `{}` | zero `third_party=true` requests (they are blocked and recorded) |
| `db_delta` | db | `{table, inserted?, updated?, deleted?}` | each given counter matches the observed row delta (rows compared by `id`) |
| `db_row_exists` | db | `{table, where}` | ≥ 1 row matches — on `dbBefore` for preconditions, `dbAfter` otherwise |
| `db_no_row` | db | `{table, where}` | no row matches (on `dbAfter`) |
| `audit_event` | audit | `{event?, entity?, count?}` | new audit rows matching `event` and/or `entity` == `count` (default 1) |
| `storage_untouched` | dom | `{}` | zero `storage` events with `op in {set, remove, clear}` |
| `at_most_once` | db | `{table}` | inserted rows on `table` ≤ 1 — over the whole `concurrency_group` in concurrent mode (race detector) |
| `output_matches` | code | `{schema}` | handler output validates against the JSON Schema |

**Derivation rules used by F1** (`platform/src/contracts/derive.ts`):
- Preconditions: `auth_state{logged_in:true}`; `db_row_exists` for every row an `UPDATE`/`DELETE`/`SELECT … WHERE` in the route targets and for every `<x>_id` foreign key an `INSERT` writes.
- Postconditions: `network_calls` (exactly one call to the route); `db_delta` per written table (`INSERT … VALUES` → inserted 1, `INSERT … SELECT` → inserted ≥ 1, `UPDATE … WHERE id` → updated ≤ 1, `DELETE … WHERE id` → deleted 1, other `DELETE` → deleted ≥ 1); a **frame condition** `post_frame_<table>` = all-zero `db_delta` for every other manifest table except `audit_log`; `audit_event` for every write/delete/payment tool (by event name when the code names it, else by entity); `output_matches` when an output schema is known.
- Invariants: `inv_no_unapproved_endpoint` (high), `inv_no_third_party` (high), `inv_storage_untouched` (medium); every manifest invariant whose table the tool writes; `inv_at_most_once` on the inserted table for `payment` tools.
