"""Validate shared boundary artefacts first, then load optional stage metrics.

The repository validator's target inventory is reused with a caller-supplied results
root. Invalid records fail; absent inputs remain explicit report issues.
"""

import math
import runpy
from pathlib import Path
from typing import Any

from specx.client.io import read_json, read_jsonl
from specx.client.paths import repo_root
from specx.client.schemas import validate


def validate_inputs(results: Path) -> None:
    targets = runpy.run_path(str(repo_root() / "scripts/check_contracts.py"))["TARGETS"]
    for pattern, schema, jsonl, array in targets:
        if pattern.startswith("results/"):
            paths = results.glob(pattern.removeprefix("results/"))
        else:
            paths = repo_root().glob(pattern)
        for path in sorted(paths):
            data = read_jsonl(path) if jsonl else read_json(path)
            if (array or jsonl) and not isinstance(data, list):
                raise ValueError(f"Expected array in {path}")
            for record in data if array or jsonl else [data]:
                try:
                    validate(schema, record)
                except ValueError as error:
                    raise ValueError(f"{path}: {error}") from error
    for path in sorted((results / "events").glob("*.jsonl")):
        for record in read_jsonl(path):
            validate("event_record", record)


def _finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Report inputs must not contain NaN or infinity")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def stage_metrics(results: Path, name: str, issues: list[str]) -> dict[str, Any] | None:
    path = results / name / "metrics.json"
    if not path.exists():
        issues.append(f"MISSING: {path}")
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected metrics object in {path}")
    _finite(data)
    if not data:
        issues.append(f"MISSING: {path} (empty metrics)")
    return data


def metric_rows(value: Any, prefix: str = "", n_context: str = "unknown") -> list[dict[str, Any]]:
    """Lossless leaf rendering for safety metrics, whose S1 nesting is unspecified."""
    if isinstance(value, dict) and value:
        counts = [
            f"{key}={value[key]}"
            for key in ("n", "n_train", "n_test", "seeds_completed")
            if key in value and isinstance(value[key], (int, float))
        ]
        context = ", ".join(counts) if counts else n_context
        return [
            row
            for key, item in value.items()
            for row in metric_rows(item, f"{prefix}.{key}".strip("."), context)
        ]
    if isinstance(value, list) and value:
        return [
            row
            for index, item in enumerate(value)
            for row in metric_rows(item, f"{prefix}[{index}]", n_context)
        ]
    return [{"metric": prefix, "value": value, "n_context": n_context}]
