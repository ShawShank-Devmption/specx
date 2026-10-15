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

## Clause kinds and their `params` (implemented by the sandbox checker, Dev A)

| kind | surface | params | passes when |
|---|---|---|---|
| `dom_exists` | dom | `{selector}` | `page.locator(selector).count() > 0` |
| `dom_absent` | dom | `{selector}` | count == 0 |
| `dom_text_contains` | dom | `{selector, text}` | inner text of selector contains `text` (case-insensitive) |
| `url_matches` | dom | `{pattern}` (regex) | `page.url()` matches |
| `auth_state` | aria | `{logged_in: bool}` | manifest's logged-in marker selector present/absent (`[data-testid=user-menu]`) |
| `network_calls` | network | `{method, path, min?, max?}` | number of matching first-party requests during+post phases within `[min,max]` (default exactly 1) |
| `no_unapproved_endpoint` | network | `{}` | zero first-party requests with `approved=false` |
| `no_third_party` | network | `{}` | zero `third_party=true` requests |
| `db_delta` | db | `{table, inserted?, updated?, deleted?}` | each given counter equals the observed delta exactly |
| `db_row_exists` | db | `{table, where}` | ≥1 row matching equality filter after the run |
| `audit_event` | audit | `{event, count?}` | audit rows with `event` since run start == count (default 1) |
| `storage_untouched` | dom | `{}` | zero `storage` events with `op in {set, remove, clear}` |
| `at_most_once` | db | `{table}` | across a `concurrency_group`, total `inserted` on `table` ≤ 1 (race-condition detector) |
| `output_matches` | code | `{schema}` | handler output validates against the JSON Schema |

Default **invariants** attached to every contract by F1: `inv_no_unapproved_endpoint` (high), `inv_no_third_party` (high), `inv_storage_untouched` (medium). Tools with `risk_level ∈ {write, delete, payment}` also get `inv_audit_event` for their entity.
