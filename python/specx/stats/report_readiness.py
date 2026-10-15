"""Held-out readiness cohorts and per-metric Holm families across apps/transitions."""

from itertools import pairwise
from pathlib import Path
from typing import Any

from specx.client.io import read_jsonl
from specx.evalx.conditions import Condition
from specx.evalx.tasks import load_tasks
from specx.stats.paired import compare_continuous, compare_success, holm, pair_trials, summarize


def readiness(
    results: Path,
    apps: list[str],
    *,
    trials: int,
    seed: int,
    issues: list[str],
    warnings: list[str],
) -> tuple[dict[str, Any], list[str]]:
    cohorts: dict[str, dict[str, list[dict[str, Any]]]] = {}
    models: set[str] = set()
    catalogue = {task.task_id: task for name in apps for task in load_tasks(name)}
    for condition in Condition:
        path = results / "trials" / f"{condition.value}.jsonl"
        cohorts[condition.value] = {name: [] for name in apps}
        if not path.exists():
            issues.append(f"MISSING: {path}")
        for row in read_jsonl(path) if path.exists() else []:
            if row["condition"] != condition.value:
                raise ValueError(f"Wrong condition in {path}")
            task = catalogue.get(row["task_id"])
            if row["app"] not in apps:
                continue
            if task is None or task.app != row["app"]:
                raise ValueError(f"Unknown/wrong-app task in {path}: {row['task_id']}")
            if row.get("split", task.split) != task.split:
                raise ValueError(f"Trial split contradicts task catalogue: {row['task_id']}")
            if task.split != "heldout":
                warnings.append(f"Excluded training trial {row['trial_id']} from readiness")
                continue
            cohorts[condition.value][row["app"]].append(row)
            models.add(row["agent_model"])
        for name in apps:
            rows = cohorts[condition.value][name]
            pair_trials(
                rows, rows
            )  # Reject duplicate task/seed identities even without a comparator.
            if len({row["tool_set_version"] for row in rows}) > 1:
                raise ValueError(f"Mixed tool revisions in {condition.value}/{name}")
            expected = {
                (task.task_id, k)
                for task in catalogue.values()
                if task.app == name and task.split == "heldout"
                for k in range(seed, seed + trials)
            }
            actual = {(row["task_id"], row["seed"]) for row in rows}
            if expected != actual:
                issues.append(
                    f"MISSING: {path} ({name}: {len(expected - actual)} expected pairs absent; "
                    f"{len(actual - expected)} unexpected pairs; n={len(rows)}/{len(expected)})"
                )
    if len(models) > 1:
        raise ValueError("Readiness requires one frozen agent model across all conditions/apps")
    comparisons: list[dict[str, Any]] = []
    conditions = list(Condition)
    for metric in ("success", "steps", "tokens"):
        family = []
        labels: list[dict[str, Any]] = []
        for name in apps:
            for left, right in pairwise(conditions):
                a, b = cohorts[left.value][name], cohorts[right.value][name]
                pairs = pair_trials(a, b)
                if not pairs:
                    issues.append(
                        f"MISSING: paired {metric} comparison {name}: {left.value} -> {right.value}"
                    )
                    continue
                if len(pairs) != len(a) or len(pairs) != len(b):
                    warnings.append(
                        f"{name} {left.value} -> {right.value}: paired n={len(pairs)}, a={len(a)}, b={len(b)}"
                    )
                family.append(
                    compare_success(a, b)
                    if metric == "success"
                    else compare_continuous(a, b, metric)
                )
                labels.append(
                    {
                        "app": name,
                        "from_condition": left.value,
                        "to_condition": right.value,
                        "holm_family": f"{metric}:all_apps_adjacent_conditions",
                    }
                )
        for label in labels:
            label["holm_family_size"] = len(family)
            label["planned_family_size"] = 3 * len(apps)
        comparisons.extend(
            {**label, **result.model_dump(mode="json")}
            for label, result in zip(labels, holm(family), strict=True)
        )
    return {
        "conditions": {
            condition: {name: summarize(rows) for name, rows in per_app.items()}
            for condition, per_app in cohorts.items()
        },
        "comparisons": comparisons,
    }, sorted(models)
