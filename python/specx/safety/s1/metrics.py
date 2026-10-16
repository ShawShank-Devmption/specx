"""Aggregate S1 fuzzing outcomes across apps, methods, and seeds."""

from collections import defaultdict
from typing import Any

import numpy as np

from specx.safety.s1.baselines import EpisodeLog

SEVERITIES = ("low", "medium", "high")


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {"mean": float(array.mean()), "sd": float(array.std(ddof=0))}


def metrics(
    logs: list[EpisodeLog], *, verdicts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Summarize seeded logs; missing time-to-find values are censored at run length."""
    if not logs:
        raise ValueError("at least one S1 log is required")
    if any(log.steps <= 0 for log in logs):
        raise ValueError("S1 logs must contain at least one step")

    verdict_by_run = {
        str(verdict["run_id"]): verdict
        for verdict in (verdicts or [])
        if isinstance(verdict.get("run_id"), str)
    }
    grouped: dict[tuple[str, str], list[EpisodeLog]] = defaultdict(list)
    method_signatures: dict[str, set[str]] = defaultdict(set)
    for log in logs:
        grouped[(log.app, log.method)].append(log)
        method_signatures[log.method].update(log.signatures)

    by_app_method: dict[str, dict[str, Any]] = {}
    for (app, method), method_logs in sorted(grouped.items()):
        rates = [1000.0 * len(log.signatures) / log.steps for log in method_logs]
        ttfv = [float(log.first_violation_step or log.steps) for log in method_logs]
        ttf_high = [float(log.first_high_step or log.steps) for log in method_logs]
        severity_mix = {severity: 0 for severity in SEVERITIES}
        run_ids = {run_id for log in method_logs for run_id in log.verdict_run_ids}
        for run_id in run_ids:
            verdict = verdict_by_run.get(run_id, {})
            for violation in verdict.get("violations", []):
                severity = violation.get("severity")
                if severity in severity_mix:
                    severity_mix[str(severity)] += 1
        by_app_method.setdefault(app, {})[method] = {
            "n": len(method_logs),
            "unique_signatures_per_1000": _summary(rates),
            "ttfv": _summary(ttfv),
            "ttf_high": _summary(ttf_high),
            "severity_mix": severity_mix,
        }

    signature_union = {
        method: sorted(signatures) for method, signatures in sorted(method_signatures.items())
    }
    method_only = {
        method: sorted(
            signatures
            - set().union(
                *(
                    other
                    for other_method, other in method_signatures.items()
                    if other_method != method
                )
            )
        )
        for method, signatures in sorted(method_signatures.items())
    }
    return {
        "by_app_method": by_app_method,
        "signature_union": signature_union,
        "method_only": method_only,
    }
