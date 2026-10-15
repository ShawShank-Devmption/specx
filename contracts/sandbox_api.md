# Sandbox HTTP API (v1) — the only runtime boundary between TypeScript and Python

Owner: **Dev A** (`platform/src/sandbox/server.ts`). Client: **`python/specx/client/sandbox.py`** (Dev C writes it in hour 1, Dev B uses it).
Transport: plain HTTP + JSON on `http://127.0.0.1:4000`. No auth. One sandbox process can hold many sessions; each session = one headless Chromium context + one seed-app DB state.

All request/response bodies are JSON. Errors: `{"error": {"code": string, "message": string}}` with HTTP 4xx/5xx (`bad_request` incl. malformed JSON, `not_found` for unknown routes, `unknown_app`, `unknown_session`, `unknown_tool`, `unknown_run`, `unknown_ref`, `scope_exceeded`, `missing_contract`, `invalid_record`, `bad_leak_kind`, `login_failed`, `app_error`, `internal`). Every response carries the header `x-specx-api-version: 1` — not a body field, so a verdict body validates against `verdict.schema.json` as-is.

## Lifecycle

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/health` | – | `{ok:true, apps:["shop","admin"], sessions:int}` |
| `POST` | `/sessions` | `{app, seed?:int, leak?:{kind,delay_ms}}` | `{session_id, app, base_url}` — starts Chromium context, logs in with manifest auth, resets DB (`POST <app>/__test/reset`), injects observers. |
| `POST` | `/sessions/{id}/reset` | `{seed?:int}` | `{ok:true}` — DB reset + new page + cleared storage; tool set unchanged. **Deterministic**: two resets with the same seed give byte-identical `/__test/db`. |
| `DELETE` | `/sessions/{id}` | – | `{ok:true}` |
| `PUT` | `/sessions/{id}/tools` | `{tools: ToolDefinition[], contracts: ToolContract[]}` | `{ok:true, count}` — loads the tool set the session will execute. Call after creation and after every F2 revision. |

## Execution

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/sessions/{id}/invoke` | `{tool_id, args, source, post_observe_ms?:int (default 1500), screenshot?:bool}` | **`Verdict`** (contracts/verdict.schema.json), `anomaly=null`. |
| `POST` | `/sessions/{id}/invoke_concurrent` | `{calls:[{tool_id,args}], source, post_observe_ms?}` | `{concurrency_group, verdicts: Verdict[]}` — all calls fired with `Promise.all` in the same page (two pages if `separate_pages:true`). Each verdict has `mode:"concurrent"`. The sandbox additionally evaluates the `at_most_once` invariant over the group. |
| `POST` | `/sessions/{id}/replay` | `{run_id}` | `Verdict` with `mode:"replay"` — resets to the recorded pre-state and re-invokes with identical args. Used for the Gate-1 determinism check. |
| `GET` | `/sessions/{id}/events?since_seq=N` | – | `{events: EventRecord[]}` — the full stream for the session, including `phase:"post"` events after the last invoke. B's S6 windower polls this. |
| `GET` | `/sessions/{id}/state` | – | `{url, db: {table: {count, rows}}, storage: {local:{}, session:{}}, aria: string, screenshot_b64?: string}` |
| `POST` | `/sessions/{id}/dom_action` | `{action:"click"|"type"|"navigate"|"press", ref?, text?, url?, key?}` | `{ok, run_id, aria, url}` — used only by the **raw_dom** eval condition. `ref` is the `[ref=eN]` id from the ARIA snapshot. Each action is recorded as its own run (`<session>_a<n>`, phases `during` then `post`, no `tool_start`), so its network effects appear in `GET …/events`; filter by `run_id`. |
| `GET` | `/sessions/{id}/example_args?tool_id=X[&seed=N]` | – | `{args: object, unsatisfied: string[]}` — **valid** arguments derived from the tool's `db_row_exists` preconditions and the current DB state. Default picks the **last** matching row; with `seed` a seeded-random matching row (S1 uses this to explore). `unsatisfied` lists precondition clause_ids no current row can satisfy (e.g. empty cart) — invoke a producer tool first. S1 mutates these in Python; the eval harness never uses this. |
| `POST` | `/sessions/{id}/apply` | `{state: object}` | `{ok:true}` — proxies to the seed app's `/__test/apply` (task setup state such as a pre-filled cart). Used by the eval harness after `reset`. |
| `POST` | `/sessions/{id}/inject_leak` | `{kind:"delayed_post"|"storage_write"|"third_party_fetch"|"background_poll", delay_ms:int}` | `{ok:true}` — proxies to the seed app's `/__test/leak`; the next tool invocation will exhibit the leak during `phase:"post"`. Used by S6 experiments. |

## Semantics the implementer must honour

1. **Verdict is computed inside the sandbox**, not by the caller: evaluate preconditions on `dbBefore` → run the handler (always, even if a precondition failed — what a tool does with bad input is evidence) → wait `post_observe_ms` → evaluate the remaining clauses → compute `effect_diff` from (db snapshot before/after, network events, mutation count, storage events, audit rows since).
2. **Which clauses are evaluated.** Single/replay mode: preconditions + invariants always; postconditions only when every precondition passed and the handler did not throw. Concurrent mode: preconditions + invariants only, because per-call postconditions cannot be attributed inside a group. Skipped clauses are omitted from `clause_results`.
3. **Status precedence**: any evaluated clause failed → `fail`; else handler threw or timed out (10 s) → `error`; else any clause evaluated to `null` → `unverifiable`; else `pass`. Failed preconditions produce violations with `category:"precondition"` — they are caller faults; S1 should not reward them.
4. **Approved**: a request is `approved=true` iff host ∈ `approved_hosts` **and** `(method, path)` matches an `approved_endpoints` entry; first-party non-fetch/xhr GETs (page loads, assets) are approved. `third_party=true` iff host ∉ `approved_hosts`. Third-party requests are **aborted** *and* recorded, so the leak is observable but harmless.
4b. **Phases**: everything recorded after a call's `tool_end` is `post` for that call (per call in concurrent mode).
5. **Violation signature** = `${tool_id}|${clause_id}|${kind}|${normalised_observed}` where `normalised_observed` strips ids, numbers inside paths and timestamps (e.g. `POST /api/analytics`, `orders x2`). S1 depends on this being stable.
6. **`sequence_prefix`** = tool_ids of all previous invokes in this session since the last reset.
7. **Determinism**: `reset` → `invoke(shop.add_to_cart,{product_id:1,qty:1})` twice must produce identical `effect_diff.db` and identical `clause_results[].passed`. `replay` re-runs reset (same seed), then silently re-applies every step since that reset (calls, concurrent groups, `apply`, `inject_leak`), then the target call. This is Gate 1.
8. **Concurrency**: each call of `invoke_concurrent` runs in its own page of the session's browser context (same cookies, same tenant) so network events are attributed per call; DB effects are measured once for the group.
9. **Isolation**: every sandbox session is a separate tenant of the seed app (cookie `specx_tenant=<session_id>` on the browser context, header `x-specx-tenant` on test-hook calls). Tenants have independent in-memory databases, audit logs and leak state, so sessions never interfere.
10. **Throughput**: ≥ 8 concurrent sessions per sandbox process; `invoke` on an `api` handler ≤ 400 ms p50 excluding `post_observe_ms`. S1 needs ~15 k invokes in the day.

## Seed-app test hooks (every seed app, Dev A)

Every hook acts on the tenant named by the `x-specx-tenant` header or `specx_tenant` cookie (default tenant `default`).

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/__test/reset` | `{seed?:int}` | `{ok:true}` — rebuilds the tenant's in-memory DB from `schema.sql` + `seed.sql` (identical for every seed; `seed` is accepted and reserved), clears audit_log and leak mode. |
| `GET` | `/__test/db` | – | `{tables: {<name>: {count:int, rows: object[]}}}` for every table in the manifest. |
| `GET` | `/__test/audit?since=<id>` | – | `{events: [{id, event, actor, entity, entity_id, ts}]}` |
| `POST` | `/__test/leak` | `{kind, delay_ms}` or `{kind:null}` | `{ok:true}` — arms a one-shot leak that fires after the next state-changing API call. |
| `POST` | `/__test/apply` | `{state: object}` | `{ok:true}` — applies task setup state (e.g. pre-filled cart). |

Leak mechanism: the next mutating API response carries header `x-telemetry: <kind>;<delay_ms>;<poll_path>`; the app's own `public/app.js` contains a telemetry module that wraps `window.fetch` (as analytics SDKs do) and performs the leak in the page after `delay_ms`. Leak kinds:
- `delayed_post` — `setTimeout(() => fetch('/api/analytics', {method:'POST'}), delay_ms)` in the page (`/api/analytics` is **not** in approved_endpoints).
- `storage_write` — `localStorage.setItem('__trk', ...)` after `delay_ms`.
- `third_party_fetch` — `fetch('https://tracker.example.invalid/p')` after `delay_ms` (blocked + recorded).
- `background_poll` — `setInterval(() => fetch(poll_path), delay_ms)` five times (`/api/cart` in shop, `/api/users` in admin; approved endpoint, but repeated → anomalous volume).
