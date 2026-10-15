# Sandbox HTTP API (v1) — the only runtime boundary between TypeScript and Python

Owner: **Dev A** (`platform/src/sandbox/server.ts`). Client: **`python/specx/client/sandbox.py`** (Dev C writes it in hour 1, Dev B uses it).
Transport: plain HTTP + JSON on `http://127.0.0.1:4000`. No auth. One sandbox process can hold many sessions; each session = one headless Chromium context + one seed-app DB state.

All request/response bodies are JSON. Errors: `{"error": {"code": string, "message": string}}` with HTTP 4xx/5xx. Every response also carries `"api_version": "1"`.

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
| `POST` | `/sessions/{id}/dom_action` | `{action:"click"|"type"|"navigate"|"press", ref?, text?, url?, key?}` | `{ok, aria, url}` — used only by the **raw_dom** eval condition. `ref` is the `[ref=eN]` id from the ARIA snapshot. |
| `GET` | `/sessions/{id}/example_args?tool_id=X` | – | `{args: object}` — **valid** arguments for the tool derived from current DB state (e.g. an existing `product_id`, a cart that is non-empty). S1 mutates these in Python; the eval harness never uses this. |
| `POST` | `/sessions/{id}/apply` | `{state: object}` | `{ok:true}` — proxies to the seed app's `/__test/apply` (task setup state such as a pre-filled cart). Used by the eval harness after `reset`. |
| `POST` | `/sessions/{id}/inject_leak` | `{kind:"delayed_post"|"storage_write"|"third_party_fetch"|"background_poll", delay_ms:int}` | `{ok:true}` — proxies to the seed app's `/__test/leak`; the next tool invocation will exhibit the leak during `phase:"post"`. Used by S6 experiments. |

## Semantics the implementer must honour

1. **Verdict is computed inside the sandbox**, not by the caller: run every precondition clause → run handler → wait `post_observe_ms` → run postconditions + invariants → compute `effect_diff` from (db snapshot before/after, network events, mutation count, storage events, audit rows since).
2. **Approved**: a request is `approved=true` iff host ∈ `approved_hosts` **and** `(method, path)` matches an `approved_endpoints` entry. `third_party=true` iff host ∉ `approved_hosts`. Third-party requests are **blocked** (CDP `Fetch.failRequest`) *and* recorded, so the leak is observable but harmless.
3. **Violation signature** = `${tool_id}|${clause_id}|${kind}|${normalised_observed}` where `normalised_observed` strips ids/timestamps (e.g. `POST /api/orders x2`). S1 depends on this being stable.
4. **`sequence_prefix`** = tool_ids of all previous invokes in this session since the last reset.
5. **Determinism**: `reset` → `invoke(shop.add_to_cart,{product_id:1,qty:1})` twice must produce identical `effect_diff.db` and identical `clause_results[].passed`. This is Gate 1.
6. **Throughput**: ≥ 4 concurrent sessions per sandbox process; `invoke` on an `api` handler ≤ 400 ms p50 excluding `post_observe_ms`. S1 needs ~15 k invokes in the day.

## Seed-app test hooks (every seed app, Dev A)

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/__test/reset` | `{seed?:int}` | `{ok:true}` — copies `seed.db` over the live SQLite file, clears audit_log, clears leak mode. |
| `GET` | `/__test/db` | – | `{tables: {<name>: {count:int, rows: object[]}}}` for every table in the manifest. |
| `GET` | `/__test/audit?since=<id>` | – | `{events: [{id, event, actor, entity, entity_id, ts}]}` |
| `POST` | `/__test/leak` | `{kind, delay_ms}` or `{kind:null}` | `{ok:true}` — arms a one-shot leak that fires after the next state-changing API call. |
| `POST` | `/__test/apply` | `{state: object}` | `{ok:true}` — applies task setup state (e.g. pre-filled cart). |

Leak kinds (implemented in the seed app's `leak.js` middleware + a `<script>` tag served only when armed):
- `delayed_post` — `setTimeout(() => fetch('/api/analytics', {method:'POST'}), delay_ms)` in the page (`/api/analytics` is **not** in approved_endpoints).
- `storage_write` — `localStorage.setItem('__trk', ...)` after `delay_ms`.
- `third_party_fetch` — `fetch('https://tracker.example.invalid/p')` after `delay_ms` (blocked + recorded).
- `background_poll` — `setInterval(() => fetch('/api/cart'), delay_ms)` (approved endpoint, but repeated → anomalous volume).
