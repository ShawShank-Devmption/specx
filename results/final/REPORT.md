# SpecX results

Generated: 2026-10-15T18:54:28.051643+00:00 · Git: 1fb0ea88cca1c434d851782175f189a12e90e78f

Status: INCOMPLETE · Evidence: unknown

Models/versions: {"agent": [], "reviser": [], "tool_set_versions": []}

Bootstrap CIs: 2,000 paired resamples, local seed 0. Holm correction uses one family per metric across apps and adjacent conditions. Missing pairs are dropped symmetrically; n is the actual matched count. Safety and task success are separate outcomes.

- Evidence is unknown: these are not validated live experimental results.

## Table 1 - Generation

| status          |
|:----------------|
| No observations |

| status                                                                                                              |
|:--------------------------------------------------------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/tools/shop.tools.json (nonempty generated tool set required)  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/tools/admin.tools.json (nonempty generated tool set required) |

## Table 2 - Verification

| status          |
|:----------------|
| No observations |

| status                                                                                                              |
|:--------------------------------------------------------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/tools/shop.tools.json (nonempty generated tool set required)  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/tools/admin.tools.json (nonempty generated tool set required) |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/verdicts/f1.jsonl (verification evidence)                     |

## Table 3 - S6 anomaly detection

| status          |
|:----------------|
| No observations |

| status                                                                |
|:----------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/s6/metrics.json |

## Table 4 - S1 adversarial fuzzing

| status          |
|:----------------|
| No observations |

| status                                                                |
|:----------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/s1/metrics.json |

## Table 5 - S2 risk prediction

| status          |
|:----------------|
| No observations |

| status                                                                |
|:----------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/s2/metrics.json |

## Table 6 - F2/S4 optimisation

| status          |
|:----------------|
| No observations |

| status                                                                                                              |
|:--------------------------------------------------------------------------------------------------------------------|
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json                                               |
| MISSING: completed /Users/ananyaganesan/specx-shawshank/results/f2/run.json                                         |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json shop/text_trace with training n>0             |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json shop/text_structured with training n>0        |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json shop/multimodal_structured with training n>0  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json admin/text_trace with training n>0            |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json admin/text_structured with training n>0       |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/f2/metrics.json admin/multimodal_structured with training n>0 |

## Table 7 - F4 readiness

| app   | condition   | n   | success % [95% CI]   | steps [95% CI]   | tokens [95% CI]   | policy % [95% CI]   | unapproved calls   | quarantined calls   |
|:------|:------------|:----|:---------------------|:-----------------|:------------------|:--------------------|:-------------------|:--------------------|
| shop  | raw_dom     | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| admin | raw_dom     | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| shop  | generated   | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| admin | generated   | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| shop  | verified    | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| admin | verified    | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| shop  | optimised   | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |
| admin | optimised   | 0   | MISSING              | MISSING          | MISSING           | MISSING             | unknown            | unknown             |

| status                                                                                                                                     |
|:-------------------------------------------------------------------------------------------------------------------------------------------|
| MISSING: completed /Users/ananyaganesan/specx-shawshank/results/evalx/run.json                                                             |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/raw_dom.jsonl                                                                 |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/raw_dom.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)    |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/raw_dom.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25)   |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/generated.jsonl                                                               |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/generated.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/generated.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25) |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/verified.jsonl                                                                |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/verified.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)   |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/verified.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/optimised.jsonl                                                               |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/optimised.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/trials/optimised.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25) |
| MISSING: paired success comparison shop: raw_dom -> generated                                                                              |
| MISSING: paired success comparison shop: generated -> verified                                                                             |
| MISSING: paired success comparison shop: verified -> optimised                                                                             |
| MISSING: paired success comparison admin: raw_dom -> generated                                                                             |
| MISSING: paired success comparison admin: generated -> verified                                                                            |
| MISSING: paired success comparison admin: verified -> optimised                                                                            |
| MISSING: paired steps comparison shop: raw_dom -> generated                                                                                |
| MISSING: paired steps comparison shop: generated -> verified                                                                               |
| MISSING: paired steps comparison shop: verified -> optimised                                                                               |
| MISSING: paired steps comparison admin: raw_dom -> generated                                                                               |
| MISSING: paired steps comparison admin: generated -> verified                                                                              |
| MISSING: paired steps comparison admin: verified -> optimised                                                                              |
| MISSING: paired tokens comparison shop: raw_dom -> generated                                                                               |
| MISSING: paired tokens comparison shop: generated -> verified                                                                              |
| MISSING: paired tokens comparison shop: verified -> optimised                                                                              |
| MISSING: paired tokens comparison admin: raw_dom -> generated                                                                              |
| MISSING: paired tokens comparison admin: generated -> verified                                                                             |
| MISSING: paired tokens comparison admin: verified -> optimised                                                                             |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/evalx/run.json optimisation_selection.shop                                           |
| MISSING: /Users/ananyaganesan/specx-shawshank/results/evalx/run.json optimisation_selection.admin                                          |

Paired comparisons (B minus A; two-sided tests):

| status          |
|:----------------|
| No observations |

## Deviations from plan

# Implementation decisions

- 2026-10-15 — C2: Holm-adjusted p-values for `[0.01, 0.04, 0.03]` are `[0.03, 0.06, 0.06]` in original order. Undefined paired standardized effects are null; success tests default to two-sided, with an explicit one-sided option for the gate.
- 2026-10-15 — C3, approved by Developer C: keep required `success_check` unchanged and add optional non-empty `success_checks`; the primary and all additional checks must pass against one final state snapshot. Submit this additive schema change as a `contracts: …` PR for shared review. Legacy task fixtures are unchanged.
- 2026-10-15 — Admin seed, confirmed by Developer C: exactly six users before task setup: `1 root/root123 admin active=1`, `2 bob/bob123 editor active=1`, `3 carol/carol123 viewer active=1`, `4 erin/erin123 viewer active=1`, `5 hank/hank123 editor active=1`, `6 ivy/ivy123 viewer active=1`. Dana, frank and gina are not seeded. Developer A owns `platform/seed-apps/admin/seed.sql` and implementation of these rows; this checkout does not contain that file or the admin schema yet.
- 2026-10-15 — C3 `admin.t10`: after a fresh reset, apply `{"users":[{"username":"dana","email":"dana@example.com","role":"viewer","active":1}]}` using the existing setup/apply interface. Developer A must support insertion by the admin `/__test/apply` hook; this does not require an HTTP API contract change. Training task `admin.t02` is never a prerequisite for held-out evaluation.
- 2026-10-15 — C3: final-state checks cannot prove that the agent listed orders/users or spoke the cart total. Those tasks retain the planned DB success criteria and state that limitation in task notes; policy compliance remains a separate C4 metric.
- 2026-10-15 — C4: the harness owns reset/setup but can reuse a caller-owned session, which remains open. Raw DOM has no generated-tool-file dependency. Trial tokens retain SDK input/output definitions; cache counts are retained separately in traces. Tool-set versions add a content digest. Policy checks use browser events even when no invocation verdict exists, and repeated unapproved requests are counted once across overlapping evidence. Shared schema fields are unchanged.
- 2026-10-15 — C5: runner persistence is trace-first and guarded against concurrent writers; resumes reject changed model/task/tool/contract/step-limit contexts or missing traces. Up to eight worker sessions are reused within each app; apps run sequentially. Run metadata/metrics default to `results/evalx`, while trial/trace locations remain unchanged. Injected offline experiments are explicitly labelled `test_double`. Replay determinism is measured only for protocol-matched F1 replays; unmatched evidence stays unknown. Live baseline numbers remain a separate required deliverable, not replaced by fixture-based results.
- 2026-10-15 — C6: harvesting includes unsafe successes as failure evidence, preserves train/held-out labels and supports explicit training-only filtering. It does not invent tool attribution, DOM changes or observed network effects. Synthetic failures are labelled pure augmentations with no executed episodes, verdicts, requests or screenshots, and are never counted as benchmark outcomes. Generated-condition live trials remain a separate required deliverable.
- 2026-10-15 — C7: implemented the text-trace arm only; C8 arms fail explicitly. Candidate filenames include a candidate index and traces have unique baseline/candidate trial IDs. The gate checks safety over all candidate episodes, not just matched pairs. Zero-pair comparisons are null and insufficient, not fictitious observations. Runs refuse existing outputs rather than attempt unsafe resume. Agent and reviser share the configured cumulative budget. Accepted training patches do not imply external re-verification, and offline test-double metrics do not substitute for the required live two-app experiment. The current S4 export contains accepted bundle/patch pairs without screenshots; C8 owns screenshot-path export.
- 2026-10-15 — C8 supersedes C7's arm/export limitations: all three arms are implemented, with one baseline per app and independent revision-zero starts. The unchanged shared patch contract is projected into a provider-compatible ops/confidence response schema, then fully validated locally; envelope/provenance fields cannot be supplied by the model. Up to three PNGs precede multimodal text; text-only arms strip images. Missing screenshots are explicit and cannot support claims of vision benefit. Accepted training evidence exports `{bundle_without_screenshot, screenshot_path, accepted_patch, arm}` with content-addressed PNG sidecars and paths relative to the dataset (null when absent). No live numbers are claimed until real experiments run.
- 2026-10-15 — C9: select the best final training-success arm independently per app from a completed F2 experiment, with ties preferring multimodal, then structured text, then text trace. Explicit arm overrides are recorded as overrides. Evaluation enforces verified revision zero, replays accepted patch histories against published final tools, preserves paired held-out cohorts and frozen model identity, and records evidence hashes for safe resume. No-accepted-patch cases explicitly report `optimised == verified` in run/metrics metadata; C10 must propagate that note into the report. Live 100-episode evaluation remains pending prerequisites and is not replaced by offline fixtures.
- 2026-10-16 — C10: reports validate shared boundary records first, return exit 2 while still publishing explicit missing-data tables for incomplete cohorts, and exclude training/gate trials from readiness. Holm families are per metric across apps/adjacent condition comparisons; actual paired n and observed/planned family sizes are retained. C9's no-accepted-patch notes propagate to report/dashboard. Safety raw JSON is preserved; S1's undocumented detailed nesting is rendered as supplied metric paths with count context, not an invented schema. The README currently shows MISSING/n=0, not benchmark claims. The dashboard is built/tested and served locally, but browser visual QA was unavailable; live experiment outputs and final coordinated commit/tag remain pending.
