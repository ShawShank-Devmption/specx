# SpecX results

Generated: 2026-10-16T15:48:22.180481+00:00 · Git: 085a31e87ac1608c88027c282e6f28ff7601068c

Status: INCOMPLETE · Evidence: unknown

Models/versions: {"agent": [], "reviser": [], "tool_set_versions": []}

Bootstrap CIs: 2,000 paired resamples, local seed 0. Holm correction uses one family per metric across apps and adjacent conditions. Missing pairs are dropped symmetrically; n is the actual matched count. Safety and task success are separate outcomes.

- Evidence is unknown: these are not validated live experimental results.

## Table 1 - Generation

| app   | tools_generated   | mean_provenance_surfaces   | tools_ge3_surfaces   |
|:------|:------------------|:---------------------------|:---------------------|
| admin | 7                 | 3.4285714285714284         | 5                    |
| shop  | 7                 | 2.857142857142857          | 3                    |

## Table 2 - Verification

| app   | verified   | quarantined   | unverifiable   | generated   | quarantine_reasons                                                                                         | replay_determinism_rate   | replay_n   | replay_total   | replay_unmatched   |
|:------|:-----------|:--------------|:---------------|:------------|:-----------------------------------------------------------------------------------------------------------|:--------------------------|:-----------|:---------------|:-------------------|
| admin | 5          | 2             | 0              | 0           | {"postcondition": 1, "precondition": 2, "side_effect": 1}                                                  | 1.0                       | 7          | 7              | 0                  |
| shop  | 4          | 3             | 0              | 0           | {"precondition": 3, "race": 1, "side_effect": 2, "storage": 1, "third_party": 1, "unapproved_endpoint": 1} | 1.0                       | 7          | 7              | 0                  |

## Table 3 - S6 anomaly detection

| metric                                    | value                              | n_context   |
|:------------------------------------------|:-----------------------------------|:------------|
| benign.fpr_both                           | 0.5                                | n=100       |
| benign.fpr_if                             | 0.5                                | n=100       |
| benign.fpr_lstm                           | 0.0                                | n=100       |
| benign.n                                  | 100                                | n=100       |
| contract_only_detection.background_poll   | 0.0                                | n_train=302 |
| contract_only_detection.delayed_post      | 1.0                                | n_train=302 |
| contract_only_detection.storage_write     | 1.0                                | n_train=302 |
| contract_only_detection.third_party_fetch | 1.0                                | n_train=302 |
| n_attempted                               | 352                                | n_train=302 |
| n_excluded                                | 50                                 | n_train=302 |
| n_train                                   | 302                                | n_train=302 |
| per_kind.background_poll.det_both         | 1.0                                | n=25        |
| per_kind.background_poll.det_if           | 0.96                               | n=25        |
| per_kind.background_poll.det_lstm         | 1.0                                | n=25        |
| per_kind.background_poll.n                | 25                                 | n=25        |
| per_kind.delayed_post.det_both            | 1.0                                | n=25        |
| per_kind.delayed_post.det_if              | 0.52                               | n=25        |
| per_kind.delayed_post.det_lstm            | 1.0                                | n=25        |
| per_kind.delayed_post.n                   | 25                                 | n=25        |
| per_kind.storage_write.det_both           | 0.52                               | n=25        |
| per_kind.storage_write.det_if             | 0.52                               | n=25        |
| per_kind.storage_write.det_lstm           | 0.0                                | n=25        |
| per_kind.storage_write.n                  | 25                                 | n=25        |
| per_kind.third_party_fetch.det_both       | 0.52                               | n=25        |
| per_kind.third_party_fetch.det_if         | 0.52                               | n=25        |
| per_kind.third_party_fetch.det_lstm       | 0.0                                | n=25        |
| per_kind.third_party_fetch.n              | 25                                 | n=25        |
| seq_len                                   | 8                                  | n_train=302 |
| split.test                                | fresh injected and benign sessions | n_train=302 |
| split.train                               | approved collection sessions       | n_train=302 |
| split.unit                                | run_id                             | n_train=302 |
| thresholds.iforest                        | 0.7159318476151784                 | n_train=302 |
| thresholds.lstm                           | 0.2846522331237793                 | n_train=302 |

## Table 4 - S1 adversarial fuzzing

| metric                                                       | value                                                                                            | n_context         |
|:-------------------------------------------------------------|:-------------------------------------------------------------------------------------------------|:------------------|
| by_app_method.admin.coverage.n                               | 1                                                                                                | n=1               |
| by_app_method.admin.coverage.severity_mix.high               | 61                                                                                               | n=1               |
| by_app_method.admin.coverage.severity_mix.low                | 0                                                                                                | n=1               |
| by_app_method.admin.coverage.severity_mix.medium             | 25                                                                                               | n=1               |
| by_app_method.admin.coverage.ttf_high.mean                   | 12.0                                                                                             | n=1               |
| by_app_method.admin.coverage.ttf_high.sd                     | 0.0                                                                                              | n=1               |
| by_app_method.admin.coverage.ttfv.mean                       | 3.0                                                                                              | n=1               |
| by_app_method.admin.coverage.ttfv.sd                         | 0.0                                                                                              | n=1               |
| by_app_method.admin.coverage.unique_signatures_per_1000.mean | 35.0                                                                                             | n=1               |
| by_app_method.admin.coverage.unique_signatures_per_1000.sd   | 0.0                                                                                              | n=1               |
| by_app_method.admin.ppo.n                                    | 1                                                                                                | n=1               |
| by_app_method.admin.ppo.severity_mix.high                    | 54                                                                                               | n=1               |
| by_app_method.admin.ppo.severity_mix.low                     | 0                                                                                                | n=1               |
| by_app_method.admin.ppo.severity_mix.medium                  | 29                                                                                               | n=1               |
| by_app_method.admin.ppo.ttf_high.mean                        | 3.0                                                                                              | n=1               |
| by_app_method.admin.ppo.ttf_high.sd                          | 0.0                                                                                              | n=1               |
| by_app_method.admin.ppo.ttfv.mean                            | 3.0                                                                                              | n=1               |
| by_app_method.admin.ppo.ttfv.sd                              | 0.0                                                                                              | n=1               |
| by_app_method.admin.ppo.unique_signatures_per_1000.mean      | 35.0                                                                                             | n=1               |
| by_app_method.admin.ppo.unique_signatures_per_1000.sd        | 0.0                                                                                              | n=1               |
| by_app_method.admin.random.n                                 | 1                                                                                                | n=1               |
| by_app_method.admin.random.severity_mix.high                 | 61                                                                                               | n=1               |
| by_app_method.admin.random.severity_mix.low                  | 0                                                                                                | n=1               |
| by_app_method.admin.random.severity_mix.medium               | 22                                                                                               | n=1               |
| by_app_method.admin.random.ttf_high.mean                     | 12.0                                                                                             | n=1               |
| by_app_method.admin.random.ttf_high.sd                       | 0.0                                                                                              | n=1               |
| by_app_method.admin.random.ttfv.mean                         | 9.0                                                                                              | n=1               |
| by_app_method.admin.random.ttfv.sd                           | 0.0                                                                                              | n=1               |
| by_app_method.admin.random.unique_signatures_per_1000.mean   | 40.0                                                                                             | n=1               |
| by_app_method.admin.random.unique_signatures_per_1000.sd     | 0.0                                                                                              | n=1               |
| by_app_method.shop.coverage.n                                | 1                                                                                                | n=1               |
| by_app_method.shop.coverage.severity_mix.high                | 39                                                                                               | n=1               |
| by_app_method.shop.coverage.severity_mix.low                 | 0                                                                                                | n=1               |
| by_app_method.shop.coverage.severity_mix.medium              | 52                                                                                               | n=1               |
| by_app_method.shop.coverage.ttf_high.mean                    | 6.0                                                                                              | n=1               |
| by_app_method.shop.coverage.ttf_high.sd                      | 0.0                                                                                              | n=1               |
| by_app_method.shop.coverage.ttfv.mean                        | 3.0                                                                                              | n=1               |
| by_app_method.shop.coverage.ttfv.sd                          | 0.0                                                                                              | n=1               |
| by_app_method.shop.coverage.unique_signatures_per_1000.mean  | 30.0                                                                                             | n=1               |
| by_app_method.shop.coverage.unique_signatures_per_1000.sd    | 0.0                                                                                              | n=1               |
| by_app_method.shop.ppo.n                                     | 1                                                                                                | n=1               |
| by_app_method.shop.ppo.severity_mix.high                     | 45                                                                                               | n=1               |
| by_app_method.shop.ppo.severity_mix.low                      | 0                                                                                                | n=1               |
| by_app_method.shop.ppo.severity_mix.medium                   | 57                                                                                               | n=1               |
| by_app_method.shop.ppo.ttf_high.mean                         | 11.0                                                                                             | n=1               |
| by_app_method.shop.ppo.ttf_high.sd                           | 0.0                                                                                              | n=1               |
| by_app_method.shop.ppo.ttfv.mean                             | 1.0                                                                                              | n=1               |
| by_app_method.shop.ppo.ttfv.sd                               | 0.0                                                                                              | n=1               |
| by_app_method.shop.ppo.unique_signatures_per_1000.mean       | 35.0                                                                                             | n=1               |
| by_app_method.shop.ppo.unique_signatures_per_1000.sd         | 0.0                                                                                              | n=1               |
| by_app_method.shop.random.n                                  | 1                                                                                                | n=1               |
| by_app_method.shop.random.severity_mix.high                  | 36                                                                                               | n=1               |
| by_app_method.shop.random.severity_mix.low                   | 0                                                                                                | n=1               |
| by_app_method.shop.random.severity_mix.medium                | 57                                                                                               | n=1               |
| by_app_method.shop.random.ttf_high.mean                      | 1.0                                                                                              | n=1               |
| by_app_method.shop.random.ttf_high.sd                        | 0.0                                                                                              | n=1               |
| by_app_method.shop.random.ttfv.mean                          | 1.0                                                                                              | n=1               |
| by_app_method.shop.random.ttfv.sd                            | 0.0                                                                                              | n=1               |
| by_app_method.shop.random.unique_signatures_per_1000.mean    | 30.0                                                                                             | n=1               |
| by_app_method.shop.random.unique_signatures_per_1000.sd      | 0.0                                                                                              | n=1               |
| method_only.coverage                                         | []                                                                                               | seeds_completed=1 |
| method_only.ppo                                              | []                                                                                               | seeds_completed=1 |
| method_only.random[0]                                        | admin.delete_user\|post_frame_notes\|db_delta\|notes inserted=0 updated=0 deleted=1              | seeds_completed=1 |
| seeds_completed                                              | 1                                                                                                | seeds_completed=1 |
| signature_union.coverage[0]                                  | admin.deactivate_user\|pre_exists_users\|db_row_exists\|users where id                           | seeds_completed=1 |
| signature_union.coverage[1]                                  | admin.delete_user\|post_frame_notes\|db_delta\|notes inserted=0 updated=0 deleted=2              | seeds_completed=1 |
| signature_union.coverage[2]                                  | admin.delete_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.coverage[3]                                  | admin.get_user\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.coverage[4]                                  | admin.set_role\|post_audit\|audit_event\|users count=0                                           | seeds_completed=1 |
| signature_union.coverage[5]                                  | admin.set_role\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.coverage[6]                                  | admin.update_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.coverage[7]                                  | shop.add_to_cart\|inv_stock_nonnegative\|db_no_row\|products where stock                         | seeds_completed=1 |
| signature_union.coverage[8]                                  | shop.add_to_cart\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.coverage[9]                                  | shop.get_product\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.coverage[10]                                 | shop.place_order\|inv_at_most_once\|at_most_once\|orders x2                                      | seeds_completed=1 |
| signature_union.coverage[11]                                 | shop.place_order\|pre_exists_cart_items\|db_row_exists\|cart_items where user_id                 | seeds_completed=1 |
| signature_union.coverage[12]                                 | shop.remove_from_cart\|pre_exists_cart_items\|db_row_exists\|cart_items where product_id,user_id | seeds_completed=1 |
| signature_union.ppo[0]                                       | admin.deactivate_user\|pre_exists_users\|db_row_exists\|users where id                           | seeds_completed=1 |
| signature_union.ppo[1]                                       | admin.delete_user\|post_frame_notes\|db_delta\|notes inserted=0 updated=0 deleted=2              | seeds_completed=1 |
| signature_union.ppo[2]                                       | admin.delete_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.ppo[3]                                       | admin.get_user\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.ppo[4]                                       | admin.set_role\|post_audit\|audit_event\|users count=0                                           | seeds_completed=1 |
| signature_union.ppo[5]                                       | admin.set_role\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.ppo[6]                                       | admin.update_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.ppo[7]                                       | shop.add_to_cart\|inv_stock_nonnegative\|db_no_row\|products where stock                         | seeds_completed=1 |
| signature_union.ppo[8]                                       | shop.add_to_cart\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.ppo[9]                                       | shop.get_product\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.ppo[10]                                      | shop.place_order\|inv_at_most_once\|at_most_once\|orders x2                                      | seeds_completed=1 |
| signature_union.ppo[11]                                      | shop.place_order\|pre_exists_cart_items\|db_row_exists\|cart_items where user_id                 | seeds_completed=1 |
| signature_union.ppo[12]                                      | shop.remove_from_cart\|inv_stock_nonnegative\|db_no_row\|products where stock                    | seeds_completed=1 |
| signature_union.ppo[13]                                      | shop.remove_from_cart\|pre_exists_cart_items\|db_row_exists\|cart_items where product_id,user_id | seeds_completed=1 |
| signature_union.random[0]                                    | admin.deactivate_user\|pre_exists_users\|db_row_exists\|users where id                           | seeds_completed=1 |
| signature_union.random[1]                                    | admin.delete_user\|post_frame_notes\|db_delta\|notes inserted=0 updated=0 deleted=1              | seeds_completed=1 |
| signature_union.random[2]                                    | admin.delete_user\|post_frame_notes\|db_delta\|notes inserted=0 updated=0 deleted=2              | seeds_completed=1 |
| signature_union.random[3]                                    | admin.delete_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.random[4]                                    | admin.get_user\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.random[5]                                    | admin.set_role\|post_audit\|audit_event\|users count=0                                           | seeds_completed=1 |
| signature_union.random[6]                                    | admin.set_role\|pre_exists_users\|db_row_exists\|users where id                                  | seeds_completed=1 |
| signature_union.random[7]                                    | admin.update_user\|pre_exists_users\|db_row_exists\|users where id                               | seeds_completed=1 |
| signature_union.random[8]                                    | shop.add_to_cart\|inv_stock_nonnegative\|db_no_row\|products where stock                         | seeds_completed=1 |
| signature_union.random[9]                                    | shop.add_to_cart\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.random[10]                                   | shop.get_product\|pre_exists_products\|db_row_exists\|products where id                          | seeds_completed=1 |
| signature_union.random[11]                                   | shop.place_order\|pre_exists_cart_items\|db_row_exists\|cart_items where user_id                 | seeds_completed=1 |
| signature_union.random[12]                                   | shop.remove_from_cart\|inv_stock_nonnegative\|db_no_row\|products where stock                    | seeds_completed=1 |
| signature_union.random[13]                                   | shop.remove_from_cart\|pre_exists_cart_items\|db_row_exists\|cart_items where product_id,user_id | seeds_completed=1 |

## Table 5 - S2 risk prediction

| metric                   | value                 | n_context                |
|:-------------------------|:----------------------|:-------------------------|
| link.gcn.auc             | 0.5                   | n_train=1221, n_test=773 |
| link.gcn.f1              | 0.6666666666666666    | n_train=1221, n_test=773 |
| link.gcn.p               | 0.5                   | n_train=1221, n_test=773 |
| link.gcn.r               | 1.0                   | n_train=1221, n_test=773 |
| link.rule.p              | 1.0                   | n_train=1221, n_test=773 |
| link.rule.r              | 0.8518518518518517    | n_train=1221, n_test=773 |
| n_test                   | 773                   | n_train=1221, n_test=773 |
| n_train                  | 1221                  | n_train=1221, n_test=773 |
| path.gcn.auc             | 0.7149472319445392    | n_train=1221, n_test=773 |
| path.gcn.f1              | 0.5407696537851366    | n_train=1221, n_test=773 |
| path.gcn.p               | 0.6563788421852937    | n_train=1221, n_test=773 |
| path.gcn.r               | 0.4606998601833152    | n_train=1221, n_test=773 |
| path.mlp.auc             | 0.8561367563131785    | n_train=1221, n_test=773 |
| path.mlp.f1              | 0.6111779987746181    | n_train=1221, n_test=773 |
| path.mlp.p               | 0.6644229168747295    | n_train=1221, n_test=773 |
| path.mlp.r               | 0.5714914519481864    | n_train=1221, n_test=773 |
| recovered_edges[0].dst   | shop.remove_from_cart | n_train=1221, n_test=773 |
| recovered_edges[0].field | product_id            | n_train=1221, n_test=773 |
| recovered_edges[0].src   | shop.list_products    | n_train=1221, n_test=773 |
| recovered_edges[1].dst   | shop.add_to_cart      | n_train=1221, n_test=773 |
| recovered_edges[1].field | product_id            | n_train=1221, n_test=773 |
| recovered_edges[1].src   | shop.list_products    | n_train=1221, n_test=773 |
| recovered_edges[2].dst   | shop.add_to_cart      | n_train=1221, n_test=773 |
| recovered_edges[2].field | product_id            | n_train=1221, n_test=773 |
| recovered_edges[2].src   | shop.get_product      | n_train=1221, n_test=773 |
| recovered_edges[3].dst   | shop.remove_from_cart | n_train=1221, n_test=773 |
| recovered_edges[3].field | product_id            | n_train=1221, n_test=773 |
| recovered_edges[3].src   | shop.get_product      | n_train=1221, n_test=773 |
| recovered_edges[4].dst   | shop.get_product      | n_train=1221, n_test=773 |
| recovered_edges[4].field | id                    | n_train=1221, n_test=773 |
| recovered_edges[4].src   | shop.view_cart        | n_train=1221, n_test=773 |

## Table 6 - F2/S4 optimisation

| status          |
|:----------------|
| No observations |

| status                                                                                                                       |
|:-----------------------------------------------------------------------------------------------------------------------------|
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json                                               |
| MISSING: completed /Users/shashankbhat/Projects/ai_project/specx/results/f2/run.json                                         |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json shop/text_trace with training n>0             |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json shop/text_structured with training n>0        |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json shop/multimodal_structured with training n>0  |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json admin/text_trace with training n>0            |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json admin/text_structured with training n>0       |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/f2/metrics.json admin/multimodal_structured with training n>0 |

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

| status                                                                                                                                              |
|:----------------------------------------------------------------------------------------------------------------------------------------------------|
| MISSING: completed /Users/shashankbhat/Projects/ai_project/specx/results/evalx/run.json                                                             |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/raw_dom.jsonl                                                                 |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/raw_dom.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)    |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/raw_dom.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25)   |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/generated.jsonl                                                               |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/generated.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/generated.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25) |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/verified.jsonl                                                                |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/verified.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)   |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/verified.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/optimised.jsonl                                                               |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/optimised.jsonl (shop: 25 expected pairs absent; 0 unexpected pairs; n=0/25)  |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/trials/optimised.jsonl (admin: 25 expected pairs absent; 0 unexpected pairs; n=0/25) |
| MISSING: paired success comparison shop: raw_dom -> generated                                                                                       |
| MISSING: paired success comparison shop: generated -> verified                                                                                      |
| MISSING: paired success comparison shop: verified -> optimised                                                                                      |
| MISSING: paired success comparison admin: raw_dom -> generated                                                                                      |
| MISSING: paired success comparison admin: generated -> verified                                                                                     |
| MISSING: paired success comparison admin: verified -> optimised                                                                                     |
| MISSING: paired steps comparison shop: raw_dom -> generated                                                                                         |
| MISSING: paired steps comparison shop: generated -> verified                                                                                        |
| MISSING: paired steps comparison shop: verified -> optimised                                                                                        |
| MISSING: paired steps comparison admin: raw_dom -> generated                                                                                        |
| MISSING: paired steps comparison admin: generated -> verified                                                                                       |
| MISSING: paired steps comparison admin: verified -> optimised                                                                                       |
| MISSING: paired tokens comparison shop: raw_dom -> generated                                                                                        |
| MISSING: paired tokens comparison shop: generated -> verified                                                                                       |
| MISSING: paired tokens comparison shop: verified -> optimised                                                                                       |
| MISSING: paired tokens comparison admin: raw_dom -> generated                                                                                       |
| MISSING: paired tokens comparison admin: generated -> verified                                                                                      |
| MISSING: paired tokens comparison admin: verified -> optimised                                                                                      |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/evalx/run.json optimisation_selection.shop                                           |
| MISSING: /Users/shashankbhat/Projects/ai_project/specx/results/evalx/run.json optimisation_selection.admin                                          |

Paired comparisons (B minus A; two-sided tests):

| status          |
|:----------------|
| No observations |

## Deviations from plan

# Decisions

## Dev C — implementation and evaluation

- 2026-10-16 — C integration: validate API v1 from `x-specx-api-version` with legacy body compatibility. Real Chromium/template F3/F1 and scripted C1/C3/C4/C5/C6 checks require no paid provider calls. Keep scripted trials outside benchmark cohorts; publish only measured generation/verification tables while F2/F4 and B metrics remain incomplete. See `docs/FREE_INTEGRATION.md`.

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
## Dev A — platform

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
