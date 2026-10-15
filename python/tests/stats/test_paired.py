"""Verify paired inference, multiplicity correction, and benchmark metric definitions."""

import json
import logging
import math
from typing import Any

import numpy as np
import pytest
from scipy.stats import wilcoxon

from specx.client.io import read_jsonl
from specx.client.paths import repo_root
from specx.stats.paired import (
    PairedResult,
    compare_continuous,
    compare_success,
    holm,
    pair_trials,
    summarize,
)


def trials(values: list[Any], metric: str = "success") -> list[dict[str, Any]]:
    return [{"task_id": "shop.t01", "seed": i, metric: value} for i, value in enumerate(values)]


def test_mcnemar_three_discordant_pairs_matches_closed_form() -> None:
    a = trials([False] * 3 + [True] * 7)
    b = trials([True] * 10)
    result = compare_success(a, b)
    assert result.n == 10
    assert result.a_mean == pytest.approx(0.7)
    assert result.b_mean == 1
    assert result.diff == pytest.approx(0.3)
    assert result.p == 2 * (0.5**3)
    assert result.effect == pytest.approx(2 * (math.asin(1) - math.asin(math.sqrt(0.7))))
    assert 0 <= result.ci_low <= result.ci_high <= 1
    assert result.test == "mcnemar_exact"
    assert result.effect_name == "cohens_h"


def test_paired_drops_missing(caplog: pytest.LogCaptureFixture) -> None:
    a, b = trials([False, False, True]), trials([True, True])
    b.append({"task_id": "admin.t01", "seed": 4, "success": False})
    with caplog.at_level(logging.WARNING):
        pairs = pair_trials(a, b)
    assert len(pairs) == 2
    assert [(x["seed"], y["seed"]) for x, y in pairs] == [(0, 0), (1, 1)]
    assert "Dropped unmatched" in caplog.text
    result = compare_success(a, b)
    assert result.n == 2 and result.a_mean == 0 and result.b_mean == 1


def test_pairing_is_order_independent_and_supports_custom_keys() -> None:
    a, b = trials([False, True, False]), trials([True, True, True])
    expected = compare_success(a, b)
    assert compare_success(list(reversed(a)), [b[1], b[2], b[0]]) == expected
    assert pair_trials([{"id": 1}], [{"id": 1}], key=("id",)) == [({"id": 1}, {"id": 1})]


@pytest.mark.parametrize("side", ["a", "b"])
def test_duplicate_pairing_keys_are_rejected(side: str) -> None:
    a, b = trials([True]), trials([False])
    (a if side == "a" else b).append({"task_id": "shop.t01", "seed": 0, "success": True})
    with pytest.raises(ValueError, match="Duplicate"):
        pair_trials(a, b)


def test_pairing_rejects_missing_key() -> None:
    with pytest.raises(ValueError, match="pairing key"):
        pair_trials([{"task_id": "shop.t01"}], trials([True]))


def test_success_identical_and_all_discordant_balanced() -> None:
    result = compare_success(trials([True, False]), trials([True, False]))
    assert result.diff == 0 and result.p == 1 and result.effect == 0
    assert result.ci_low == result.ci_high == 0
    balanced = compare_success(trials([True, False]), trials([False, True]))
    assert balanced.diff == 0 and balanced.p == 1


def test_success_one_sided_is_explicit_and_directional() -> None:
    before, after = trials([False] * 6 + [True] * 4), trials([True] * 10)
    assert compare_success(before, after).p == pytest.approx(2 / 64)
    assert compare_success(before, after, alternative="greater").p == pytest.approx(1 / 64)
    assert compare_success(after, before, alternative="greater").p == 1


def test_compare_continuous_matches_wilcoxon_and_paired_effect() -> None:
    a, b = trials([3, 6, 2, 8, 4], "steps"), trials([1, 3, 2, 4, 2], "steps")
    result = compare_continuous(a, b, "steps")
    differences = np.array([-2, -3, 0, -4, -2])
    assert result.diff == pytest.approx(float(differences.mean()))
    assert result.p == pytest.approx(wilcoxon(differences, zero_method="zsplit").pvalue)
    assert result.effect == pytest.approx(differences.mean() / differences.std(ddof=1))
    assert result.effect_name == "cohens_dz"
    assert result.test == "wilcoxon_signed_rank"
    assert compare_continuous(list(reversed(a)), list(reversed(b)), "steps") == result


def test_continuous_identical_lists() -> None:
    a = trials([1, 3, 2, 4], "steps")
    result = compare_continuous(a, a, "steps")
    assert result.diff == 0 and result.p == 1 and result.effect == 0
    assert result.ci_low == result.ci_high == 0


def test_constant_nonzero_difference_has_undefined_standardized_effect() -> None:
    result = compare_continuous(trials([3, 3, 3], "steps"), trials([1, 1, 1], "steps"), "steps")
    assert result.diff == -2 and result.effect is None
    assert result.ci_low == result.ci_high == -2
    json.dumps(result.model_dump(), allow_nan=False)


def test_total_tokens_derive_from_input_and_output() -> None:
    a = [{"task_id": "shop.t01", "seed": 0, "input_tokens": 100, "output_tokens": 20}]
    b = [{"task_id": "shop.t01", "seed": 0, "input_tokens": 50, "output_tokens": 10}]
    result = compare_continuous(a, b, "tokens")
    assert result.a_mean == 120 and result.b_mean == 60 and result.diff == -60
    assert result.effect is None


def result_with_p(p: float) -> PairedResult:
    return PairedResult(
        n=10,
        metric="success",
        a_mean=0,
        b_mean=1,
        diff=1,
        ci_low=1,
        ci_high=1,
        p=p,
        effect=math.pi,
        effect_name="cohens_h",
        test="mcnemar_exact",
    )


def test_holm_corrects_in_original_order_without_mutating_inputs() -> None:
    original = [result_with_p(p) for p in [0.01, 0.04, 0.03]]
    corrected = holm(original)
    assert [r.p_holm for r in corrected] == pytest.approx([0.03, 0.06, 0.06])
    assert all(r.p_holm is None for r in original)
    assert holm([]) == []


def test_holm_ties_and_clipping() -> None:
    assert [r.p_holm for r in holm([result_with_p(p) for p in [0.5, 1, 0.5]])] == [1, 1, 1]


def test_bootstrap_resamples_paired_differences_with_fixed_seed() -> None:
    a, b = trials([False, True, False, True]), trials([True, True, True, False])
    differences = np.array([1, 0, 1, -1])
    rng = np.random.default_rng(0)
    means = differences[rng.integers(0, 4, size=(2000, 4))].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    result = compare_success(a, b)
    assert (result.ci_low, result.ci_high) == (low, high)


def test_summarize_means_and_episode_incidence_rates() -> None:
    records = read_jsonl(repo_root() / "fixtures/trials/sample.trials.jsonl")
    # Distinct seeds keep this a single-condition sample rather than duplicate pairs.
    for seed, record in enumerate(records):
        record["seed"] = seed
    records[0]["policy_violations"] = [{"kind": "forbidden_action"}] * 3
    records[0]["unapproved_calls"] = 4
    records[0]["quarantined_tool_calls"] = 2
    summary = summarize(records)
    assert summary["n"] == 4 and summary["success_rate"] == 0.75
    assert summary["mean_steps"] == 6.5
    assert summary["mean_tokens"] == (43100 + 10400 + 10740 + 8310) / 4
    assert summary["policy_violation_rate"] == 0.5  # incidence, not violation count
    assert summary["unapproved_rate"] == 0.25
    assert summary["unapproved_calls"] == 4 and summary["quarantined_tool_calls"] == 2
    for metric in (
        "success_rate",
        "mean_steps",
        "mean_tokens",
        "policy_violation_rate",
        "unapproved_rate",
    ):
        assert len(summary[f"{metric}_ci"]) == 2
    assert summarize(records) == summary
    json.dumps(summary, allow_nan=False)


def test_empty_summary_is_explicit_and_json_safe() -> None:
    summary = summarize([])
    assert summary["n"] == 0 and summary["success_rate"] is None
    assert summary["success_rate_ci"] == [None, None]
    json.dumps(summary, allow_nan=False)


@pytest.mark.parametrize(
    "compare", [compare_success, lambda a, b: compare_continuous(a, b, "steps")]
)
def test_comparisons_reject_empty_pair_sets(compare: Any) -> None:
    with pytest.raises(ValueError, match="No paired trials"):
        compare([], [])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "3", True])
def test_continuous_rejects_nonfinite_or_nonnumeric_values(value: Any) -> None:
    with pytest.raises(ValueError, match="finite number"):
        compare_continuous(trials([value], "steps"), trials([1], "steps"), "steps")


def test_success_rejects_missing_and_nonboolean_outcomes() -> None:
    with pytest.raises(ValueError, match="success"):
        compare_success(trials([1]), trials([True]))
    with pytest.raises(ValueError, match="success"):
        compare_success(trials([1], "steps"), trials([True]))


def test_continuous_drops_missing_pairs_before_reading_metrics() -> None:
    a = [*trials([1, 2], "steps"), {"task_id": "shop.t02", "seed": 1}]
    b = trials([1, 1], "steps")
    result = compare_continuous(a, b, "steps")
    assert result.n == 2 and result.diff == -0.5


def test_summaries_are_order_independent_and_bootstrap_does_not_change_global_rng() -> None:
    records = read_jsonl(repo_root() / "fixtures/trials/sample.trials.jsonl")
    np.random.seed(17)
    before = np.random.get_state()
    assert summarize(records) == summarize(list(reversed(records)))
    compare_success(trials([False, True]), trials([True, True]))
    after = np.random.get_state()
    assert before[0] == after[0] and np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]


@pytest.mark.parametrize("count", [-1, 1.5])
def test_summary_rejects_invalid_safety_counts(count: float) -> None:
    record = read_jsonl(repo_root() / "fixtures/trials/sample.trials.jsonl")[0]
    record["unapproved_calls"] = count
    with pytest.raises(ValueError, match="non-negative integer"):
        summarize([record])
