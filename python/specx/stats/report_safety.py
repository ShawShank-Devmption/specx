"""Check documented safety metrics without imposing an invented S1 JSON nesting."""

from pathlib import Path
from typing import Any

from specx.stats.report_inputs import metric_rows

LEAKS = ("delayed_post", "storage_write", "third_party_fetch", "background_poll")


def safety_checks(
    data: dict[str, Any] | None, stage: str, issues: list[str], results: Path
) -> None:
    if data is None:
        return
    source = results / stage / "metrics.json"

    def require(record: Any, keys: tuple[str, ...], path: str) -> dict[str, Any]:
        if not isinstance(record, dict) or not record:
            issues.append(f"MISSING: {source} {path} nonempty object")
            return {}
        for key in keys:
            if key not in record:
                issues.append(f"MISSING: {source} {path}.{key}")
        return record

    # Full JSON numeric bounds are local because safety metrics have no shared schema.
    for row in metric_rows(data):
        leaf, value = row["metric"].split(".")[-1], row["value"]
        if leaf in ("n", "n_train", "n_test", "seeds_completed"):
            if type(value) is not int or value < 0:
                raise ValueError(f"{source}: {row['metric']} must be a nonnegative integer")
            if value == 0:
                issues.append(f"MISSING: {source} {row['metric']} has n=0")
        if (
            leaf in ("auc", "p", "r", "precision", "recall", "f1")
            or leaf.startswith(("det_", "fpr_"))
        ) and (type(value) not in (int, float) or not 0 <= value <= 1):
            raise ValueError(f"{source}: {row['metric']} must be a rate in [0, 1]")
    if stage == "s6":
        require(
            data, ("n_train", "thresholds", "per_kind", "benign", "contract_only_detection"), "root"
        )
        require(data.get("thresholds"), ("iforest", "lstm"), "thresholds")
        per_kind = require(data.get("per_kind"), LEAKS, "per_kind")
        contract = require(data.get("contract_only_detection"), LEAKS, "contract_only_detection")
        for kind in LEAKS:
            require(per_kind.get(kind), ("n", "det_if", "det_lstm", "det_both"), f"per_kind.{kind}")
            if kind in contract and (
                type(contract[kind]) not in (float, int) or not 0 <= contract[kind] <= 1
            ):
                raise ValueError(f"{source}: invalid contract-only detection rate")
        require(data.get("benign"), ("n", "fpr_if", "fpr_lstm", "fpr_both"), "benign")
    elif stage == "s2":
        require(data, ("n_train", "n_test", "link", "path", "recovered_edges"), "root")
        link = require(data.get("link"), ("rule", "gcn"), "link")
        path = require(data.get("path"), ("mlp", "gcn"), "path")
        require(link.get("rule"), ("p", "r"), "link.rule")
        for record, label in (
            (link.get("gcn"), "link.gcn"),
            (path.get("mlp"), "path.mlp"),
            (path.get("gcn"), "path.gcn"),
        ):
            require(record, ("auc", "p", "r", "f1"), label)
    else:
        # B specifies method names and metrics but not their JSON nesting.
        text = str(data).lower()
        for method in ("random", "coverage", "ppo"):
            if method not in text:
                issues.append(f"MISSING: {source} method {method}")
        if not any(
            row["metric"].split(".")[-1] in ("n", "seeds_completed") for row in metric_rows(data)
        ):
            issues.append(f"MISSING: {source} sample/seed counts (S1 JSON layout is unspecified)")
