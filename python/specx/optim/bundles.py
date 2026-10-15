"""Harvest failed/unsafe episodes and expose pure, labelled synthetic injections.

No browser/model is called here. Held-out provenance is retained so the reviser can
enforce the training-only boundary; split='train' explicitly filters source episodes.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from specx.client.io import read_jsonl
from specx.client.schemas import validate
from specx.optim.bundle_records import FailureBundle
from specx.optim.bundle_synthetic import synthetic_failures
from specx.optim.bundle_trace import (
    aria_diff,
    aria_snapshots,
    failing_steps,
    load_trace,
    network_log,
    transcript_tail,
)

__all__ = ["FailureBundle", "harvest", "synthetic_failures"]


def _index(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {}
    names = set()
    for tool in tools:
        validate("tool_definition", tool)
        if tool["tool_id"] in indexed:
            raise ValueError(f"Duplicate tool_id: {tool['tool_id']}")
        if (tool["app"], tool["name"]) in names:
            raise ValueError(f"Duplicate tool name for {tool['app']}: {tool['name']}")
        names.add((tool["app"], tool["name"]))
        indexed[tool["tool_id"]] = tool
    return indexed


def _tool_ids(
    trial: dict[str, Any],
    trace: dict[str, Any],
    steps: list[dict[str, Any]],
    indexed: dict[str, dict[str, Any]],
) -> list[str]:
    by_name = {
        tool["name"]: tool["tool_id"] for tool in indexed.values() if tool["app"] == trial["app"]
    }
    if trial["condition"] == "raw_dom":
        by_name = {}
    ids = [
        step["tool_id"] if step.get("tool_id") is not None else by_name.get(step.get("name", ""))
        for step in steps
    ]
    ids.extend(
        verdict["tool_id"]
        for verdict in trace.get("verdicts", [])
        if verdict["status"] != "pass" or verdict["violations"]
    )
    for identity in ids:
        if identity is not None and (
            identity not in indexed or indexed[identity]["app"] != trial["app"]
        ):
            raise ValueError(f"Trace references an unknown or wrong-app tool: {identity}")
    return list(dict.fromkeys(identity for identity in ids if identity is not None))


def harvest(
    trials_path: Path,
    traces_dir: Path,
    tools: list[dict[str, Any]],
    *,
    only_failures: bool = True,
    split: Literal["train", "heldout"] | None = None,
) -> list[FailureBundle]:
    indexed = _index(tools)
    bundles = []
    seen = set()
    if split not in (None, "train", "heldout"):
        raise ValueError("split must be train, heldout or None")
    for trial in read_jsonl(trials_path):
        validate("trial_result", trial)
        if trial["trial_id"] in seen:
            raise ValueError(f"Duplicate trial_id: {trial['trial_id']}")
        seen.add(trial["trial_id"])
        if split is not None and trial.get("split") != split:
            continue
        unsafe = bool(
            trial["policy_violations"]
            or trial["unapproved_calls"]
            or trial["quarantined_tool_calls"]
        )
        if only_failures and trial["success"] and not unsafe:
            continue
        trace = load_trace(trial, traces_dir)
        steps = failing_steps(trial, trace)
        ids = _tool_ids(trial, trace, steps, indexed)
        before, after = aria_snapshots(trace, steps)
        reason = trial.get("failure_reason", "wrong_tool" if not trial["success"] else "none")
        if unsafe and reason == "none":
            reason = "policy_violation"
        bundles.append(
            FailureBundle(
                trial_id=trial["trial_id"],
                task_id=trial["task_id"],
                tool_ids=ids,
                tools=[deepcopy(indexed[identity]) for identity in ids],
                transcript_tail=transcript_tail(trace.get("messages", [])),
                verdicts=deepcopy(trace.get("verdicts", [])),
                aria_before=before,
                aria_after=after,
                dom_diff=aria_diff(before, after),
                network_log=network_log(trace, steps),
                screenshot_b64=trace.get("final_screenshot_b64"),
                failure_reason=reason,
                split=trial.get("split"),
            )
        )
    return bundles
