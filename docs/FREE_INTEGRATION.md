# Developer C — no-paid-API integration checkpoint

Validated locally on 2026-10-16. No Anthropic requests were made. Developer A's
platform and Developer B's available S1/S6 code were integrated into local `Ananya`;
these integration commits have not been pushed. Existing dashboard edits were preserved.

## Verified results

| Check | Observed result |
|---|---|
| Python offline suite, including available B code | 276 passed |
| Python real-sandbox suite with scripted responses | 27 passed |
| Platform suite with real Chromium integration enabled | 130 passed |
| Dashboard tests and production build | 6 passed; build passed |
| Shared schema validation after generation/verification | 165 records, 22 files, 9 schemas passed |
| Template generation | 7 tools per app; no model-assisted naming |
| F1 verification, Shop | 6 verified; checkout quarantined for concurrent duplicate orders |
| F1 verification, Admin | 5 verified; role change quarantined for missing audit; deletion for note cascade |
| Replay determinism | 7/7 per app |
| Workflow graph construction | Shop: 7 nodes / 8 edges; Admin: 7 nodes / 55 edges |

The Python integration tests exercise all 20 mechanical task goals on fresh real
state, the exact six seeded admin users, Dana setup, tenant isolation, reset,
screenshots, replay, event cursors, error handling, generated-tool agent execution,
and raw-DOM checkout policy detection. They also harvest a real unsafe-success trace
into a C6 failure bundle, validate its PNG, and enforce held-out exclusion from
training evidence. The runner smoke test persists an actual sandbox episode using
scripted responses.

Integration fixes: C1 now validates the platform's API-version response header while
retaining legacy body support. C5's extraction test respects A's concurrent verdict
semantics (preconditions and invariants, not postconditions). The old live smoke
test loads only fixture tools with matching contracts; shared fixtures intentionally
contain a partial contract set.

## C1–C10 status at this checkpoint

| Task | Validated without paid calls | Still pending |
|---|---|---|
| C1 | Client, schemas, fake sandbox, actual HTTP integration | Shared-team merge/review coordination |
| C2 | Statistics engine and regression tests | Nothing requiring a model |
| C3 | All 20 task definitions and real-state success checks | Shared `success_checks` contract PR/review |
| C4 | Scripted agent, tool transport, raw-DOM policy, screenshots | Actual provider/agent smoke run |
| C5 | Runner persistence, resume tests, real tables 1–2 extraction | 50 real-model raw-DOM episodes |
| C6 | Failure harvesting, real browser evidence, synthetic augmentation | 50 real-model generated episodes |
| C7 | Patch application and paired safety gate offline tests | Real text-trace optimisation experiment |
| C8 | Three-arm wiring, structured schema, PNG handling/export tests | Real three-arm model comparison |
| C9 | Selection, provenance and evaluation/resume tests | Completed F2 evidence and real 100-episode evaluation |
| C10 | Partial report, measured tables 1–2, dashboard tests/build | B's S6/S1/S2 metrics and real F2/F4 cohorts |

The report intentionally exits **2** with **44 missing inputs**. It publishes useful
partial tables, not a completed benchmark. Scripted tests are not benchmark samples,
not evidence of model readiness, and not accepted optimisation patches. F1 alone is
not full S1/S6 hardening. B's full collection/orchestration, PPO and S2 runners are
not present on the integrated B branch; their metrics cannot yet be produced.

## Repeat without paid calls

Install dependencies first (`make setup`; package downloads, not model inference).
Start `make apps` and `make sandbox` in separate terminals. Then:

```bash
make generate-free        # explicitly --namer template; replaces generated tool files
make verify               # real browser contract checks; appends F1 verdicts
make graph                # rebuild graphs from available evidence
make test-free-integration
make report               # exit 2 expected until missing experiment inputs exist
```

`make baseline`, `make optimise`, `make evaluate` and `make demo` are **not** part
of this no-paid-call workflow. Do not run them until model access/spend is approved.
Keep generated experiment artefacts under `results/`; the tracked partial report
and dashboard JSON do not embed scripted trials as real experiment observations.
