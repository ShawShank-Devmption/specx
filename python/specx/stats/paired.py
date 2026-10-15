"""Paired inference shared by the regression gate, benchmark and safety ablations.

Differences and effects always mean B minus A. Tests default to two-sided;
the gate can explicitly request a one-sided success test. CIs are percentile
bootstraps of paired differences (2,000 resamples, local seed 0).
"""

import logging
import math
from numbers import Real
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import binomtest, wilcoxon

Alternative = Literal["two-sided", "greater", "less"]
Trial = dict[str, Any]


class PairedResult(BaseModel):
    """A comparison on matched trials; null effect means Cohen's dz is undefined.

    In particular, a nonzero constant difference or a single pair has no estimable
    standard deviation. Null avoids emitting infinity/NaN or claiming zero effect.
    """

    model_config = ConfigDict(allow_inf_nan=False)
    n: int = Field(ge=1)
    metric: str
    a_mean: float
    b_mean: float
    diff: float
    ci_low: float
    ci_high: float
    p: float = Field(ge=0, le=1)
    p_holm: float | None = Field(default=None, ge=0, le=1)
    effect: float | None
    effect_name: str
    test: str
    alternative: Alternative = "two-sided"


class _Summary(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    n: int
    success_rate: float | None
    mean_steps: float | None
    mean_tokens: float | None
    policy_violation_rate: float | None
    unapproved_rate: float | None
    success_rate_ci: tuple[float | None, float | None]
    mean_steps_ci: tuple[float | None, float | None]
    mean_tokens_ci: tuple[float | None, float | None]
    policy_violation_rate_ci: tuple[float | None, float | None]
    unapproved_rate_ci: tuple[float | None, float | None]
    unapproved_calls: int
    quarantined_tool_calls: int


def pair_trials(
    a: list[Trial], b: list[Trial], key: tuple[str, ...] = ("task_id", "seed")
) -> list[tuple[Trial, Trial]]:
    """Inner-join unique trial keys, logging unmatched keys and rejecting duplicates.

    Canonical ordering keeps seeded confidence intervals independent of input order.
    Callers must select one condition/revision per side before comparing.
    """
    if not key:
        raise ValueError("A pairing key must contain at least one field")

    def index(records: list[Trial], side: str) -> dict[tuple[Any, ...], Trial]:
        indexed = {}
        for record in records:
            try:
                identity = tuple(record[field] for field in key)
                hash(identity)
            except (KeyError, TypeError) as error:
                raise ValueError(f"Invalid pairing key {key!r} in {side} trial") from error
            if identity in indexed:
                raise ValueError(f"Duplicate pairing key in {side}: {identity!r}")
            indexed[identity] = record
        return indexed

    left, right = index(a, "a"), index(b, "b")
    only_a, only_b = left.keys() - right.keys(), right.keys() - left.keys()
    if only_a or only_b:
        logging.getLogger(__name__).warning(
            "Dropped unmatched pairing keys: a=%s; b=%s",
            sorted(only_a, key=repr),
            sorted(only_b, key=repr),
        )
    return [
        (left[identity], right[identity])
        for identity in sorted(left.keys() & right.keys(), key=repr)
    ]


def _matched(a: list[Trial], b: list[Trial]) -> tuple[list[Trial], list[Trial]]:
    pairs = pair_trials(a, b)
    if not pairs:
        raise ValueError("No paired trials available for comparison")
    return [left for left, _ in pairs], [right for _, right in pairs]


def _number(trial: Trial, metric: str) -> float:
    if metric == "tokens":
        return _number(trial, "input_tokens") + _number(trial, "output_tokens")
    value = trial.get(metric)
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{metric} must be a finite number, got {value!r}")
    return float(value)


def _success(trial: Trial) -> float:
    value = trial.get("success")
    if type(value) is not bool:
        raise ValueError(f"success must be a boolean, got {value!r}")
    return float(value)


def _bootstrap_ci(values: NDArray[np.float64]) -> tuple[float, float]:
    rng = np.random.default_rng(0)
    # Bound temporary memory even when B summarizes thousands of observations.
    means = []
    for start in range(0, 2000, 128):
        indices = rng.integers(0, len(values), size=(min(128, 2000 - start), len(values)))
        means.append(values[indices].mean(axis=1))
    low, high = np.quantile(np.concatenate(means), [0.025, 0.975])
    return float(low), float(high)


def compare_success(
    a: list[Trial], b: list[Trial], *, alternative: Alternative = "two-sided"
) -> PairedResult:
    """Exact McNemar: binomial test of B wins among discordant pairs.

    alternative='greater' tests whether B improves success over A (for the F2 gate).
    """
    if alternative not in ("two-sided", "greater", "less"):
        raise ValueError(f"Unknown test alternative: {alternative!r}")
    left, right = _matched(a, b)
    x = np.array([_success(trial) for trial in left], dtype=float)
    y = np.array([_success(trial) for trial in right], dtype=float)
    wins, losses = int(np.sum(y > x)), int(np.sum(x > y))
    p = (
        float(binomtest(wins, wins + losses, p=0.5, alternative=alternative).pvalue)
        if wins + losses
        else 1.0
    )
    low, high = _bootstrap_ci(y - x)
    a_mean, b_mean = float(x.mean()), float(y.mean())
    return PairedResult(
        n=len(x),
        metric="success",
        a_mean=a_mean,
        b_mean=b_mean,
        diff=float((y - x).mean()),
        ci_low=low,
        ci_high=high,
        p=p,
        effect=2 * (math.asin(math.sqrt(b_mean)) - math.asin(math.sqrt(a_mean))),
        effect_name="cohens_h",
        test="mcnemar_exact",
        alternative=alternative,
    )


def compare_continuous(a: list[Trial], b: list[Trial], metric: str) -> PairedResult:
    """Wilcoxon with split zero ranks, paired Cohen's dz, and paired mean-difference CI.

    Use metric='tokens' for input_tokens + output_tokens; other numeric fields are read
    directly. Identical pairs return p=1 and effect=0 without invoking Wilcoxon.
    """
    left, right = _matched(a, b)
    x = np.array([_number(trial, metric) for trial in left], dtype=float)
    y = np.array([_number(trial, metric) for trial in right], dtype=float)
    differences = y - x
    identical = bool(np.all(differences == 0))
    p = (
        1.0
        if identical
        else float(wilcoxon(differences, zero_method="zsplit", alternative="two-sided").pvalue)
    )
    deviation = float(differences.std(ddof=1)) if len(differences) > 1 else 0.0
    effect = 0.0 if identical else float(differences.mean() / deviation) if deviation else None
    low, high = _bootstrap_ci(differences)
    return PairedResult(
        n=len(x),
        metric=metric,
        a_mean=float(x.mean()),
        b_mean=float(y.mean()),
        diff=float(differences.mean()),
        ci_low=low,
        ci_high=high,
        p=p,
        effect=effect,
        effect_name="cohens_dz",
        test="wilcoxon_signed_rank",
    )


def holm(results: list[PairedResult]) -> list[PairedResult]:
    """Adjust one comparison family with monotone Holm step-down p-values.

    Return copies in the input order so callers can reuse raw results in another family.
    """
    corrected = list(results)
    running = 0.0
    for rank, index in enumerate(sorted(range(len(results)), key=lambda i: results[i].p)):
        running = min(1.0, max(running, (len(results) - rank) * results[index].p))
        corrected[index] = results[index].model_copy(update={"p_holm": running})
    return corrected


def _count(trial: Trial, metric: str) -> int:
    value = _number(trial, metric)
    if value < 0 or not value.is_integer():
        raise ValueError(f"{metric} must be a non-negative integer")
    return int(value)


def summarize(trials: list[Trial]) -> dict[str, Any]:
    """Summarize all supplied episodes, including failed and policy-violating ones.

    Rates are fractions of episodes: policy rate means >=1 policy violation and
    unapproved rate means >=1 unapproved call. *_ci values are 95% [low, high] lists.
    No observations yields n=0 and null estimates/CIs, never fictitious zero rates.
    """
    values: dict[str, list[float]] = {
        metric: []
        for metric in (
            "success_rate",
            "mean_steps",
            "mean_tokens",
            "policy_violation_rate",
            "unapproved_rate",
        )
    }
    unapproved_total = quarantined_total = 0
    for trial in trials:
        policy = trial.get("policy_violations")
        if not isinstance(policy, list):
            raise ValueError("policy_violations must be a list")
        unapproved = _count(trial, "unapproved_calls")
        quarantined = _count(trial, "quarantined_tool_calls")
        values["success_rate"].append(_success(trial))
        values["mean_steps"].append(_number(trial, "steps"))
        values["mean_tokens"].append(_number(trial, "tokens"))
        values["policy_violation_rate"].append(float(bool(policy)))
        values["unapproved_rate"].append(float(unapproved > 0))
        unapproved_total += unapproved
        quarantined_total += quarantined
    estimates: dict[str, Any] = {
        "n": len(trials),
        "unapproved_calls": unapproved_total,
        "quarantined_tool_calls": quarantined_total,
    }
    for metric, observations in values.items():
        # Canonical order also makes seeded single-condition summaries reproducible.
        array = np.array(sorted(observations), dtype=float)
        estimates[metric] = float(array.mean()) if len(array) else None
        estimates[f"{metric}_ci"] = _bootstrap_ci(array) if len(array) else (None, None)
    return _Summary(**estimates).model_dump(mode="json")
