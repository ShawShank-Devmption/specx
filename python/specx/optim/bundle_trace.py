"""Read and focus observed traces without inventing missing failure evidence.

Only bounded copies are returned; source transcripts and browser records stay intact.
"""

import json
import re
from collections import Counter
from copy import deepcopy
from difflib import unified_diff
from pathlib import Path
from typing import Any

from specx.client.io import read_json
from specx.client.schemas import validate


def bounded(text: str, limit: int) -> str:
    marker = "...[truncated]"
    return text if len(text) <= limit else text[: limit - len(marker)] + marker


def transcript_tail(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tail = deepcopy(messages[-6:])
    for message in tail:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                body = block.get("content", "")
                text = (
                    body
                    if isinstance(body, str)
                    else json.dumps(body, sort_keys=True, allow_nan=False)
                )
                block["content"] = bounded(text, 2000)
    return tail


def aria_diff(before: str, after: str) -> str:
    return bounded(
        "\n".join(
            unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile="aria_before",
                tofile="aria_after",
                lineterm="",
            )
        ),
        4000,
    )


def load_trace(trial: dict[str, Any], directory: Path) -> dict[str, Any]:
    identity = trial["trial_id"]
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", identity):
        raise ValueError(f"Unsafe trial_id for trace lookup: {identity!r}")
    filename = f"{identity}.json"
    if trial.get("trace_path") and Path(trial["trace_path"]).name != filename:
        raise ValueError(f"Trial trace_path does not match trial_id: {identity}")
    path = directory / filename
    if path.resolve().parent != directory.resolve():
        raise ValueError(f"Trace must remain inside the supplied directory: {identity}")
    trace = read_json(path)
    if not isinstance(trace, dict):
        raise ValueError(f"Expected trace object for {identity}")
    for key in ("trial_id", "task_id"):
        if trace.get(key) != trial[key]:
            raise ValueError(f"Trace {key} mismatch for {identity}")
    for key in ("app", "condition", "seed", "agent_model", "tool_set_version"):
        if key in trace and trace[key] != trial[key]:
            raise ValueError(f"Trace {key} mismatch for {identity}")
    source_task = trace.get("task")
    if (
        isinstance(source_task, dict)
        and "split" in source_task
        and "split" in trial
        and source_task["split"] != trial["split"]
    ):
        raise ValueError(f"Trace split mismatch for {identity}")
    for key in ("messages", "verdicts", "events"):
        records = trace.get(key) if key == "messages" else trace.get(key, [])
        if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
            raise ValueError(f"Trace {key} must be an array of objects")
    for verdict in trace.get("verdicts", []):
        validate("verdict", verdict)
        if verdict["app"] != trial["app"]:
            raise ValueError(f"Verdict app mismatch for {identity}")
    for event in trace.get("events", []):
        validate("event_record", event)
    return trace


def failing_steps(trial: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    steps = trace.get("step_log", trace.get("tool_calls", []))
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        raise ValueError("Trace tool steps must be an array of objects")
    runs = {
        verdict["run_id"]
        for verdict in trace.get("verdicts", [])
        if verdict["status"] != "pass" or verdict["violations"]
    }
    policy_steps = {
        violation["step"] for violation in trial["policy_violations"] if "step" in violation
    }
    failures = [
        step
        for step in steps
        if step.get("error_code")
        or step.get("verdict_run_id") in runs
        or step.get("tool_status") == "quarantined"
        or step.get("step") in policy_steps
    ]
    # A final-state failure may follow individually passing calls; retain those actions.
    return failures or steps


def aria_snapshots(trace: dict[str, Any], steps: list[dict[str, Any]]) -> tuple[str, str]:
    before = (
        steps[0].get("aria_before", trace.get("aria_before")) if steps else trace.get("aria_before")
    )
    after = (
        steps[-1].get("aria_after", trace.get("aria_after")) if steps else trace.get("aria_after")
    )
    if not isinstance(before, str) or not isinstance(after, str):
        raise ValueError("Trace must provide before/after ARIA snapshots")
    return before, after


def network_log(trace: dict[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs = {step["verdict_run_id"] for step in steps if step.get("verdict_run_id")}
    if not runs:
        runs = {
            verdict["run_id"]
            for verdict in trace.get("verdicts", [])
            if verdict["status"] != "pass" or verdict["violations"]
        }
    if not runs:
        tool_ids = {
            step["tool_id"] for step in steps if step.get("tool_id") and not step.get("error_code")
        }
        runs = {
            verdict["run_id"]
            for verdict in trace.get("verdicts", [])
            if not steps or verdict["tool_id"] in tool_ids
        }
    selected = [verdict for verdict in trace.get("verdicts", []) if verdict["run_id"] in runs]
    seqs = {seq for step in steps for seq in step.get("event_seqs", [])}
    scoped = any("event_seqs" in step or "verdict_run_id" in step for step in steps)
    result: list[dict[str, Any]] = []
    from_verdicts: Counter[tuple[str, str, str, str]] = Counter()

    def key(run_id: str, request: dict[str, Any]) -> tuple[str, str, str, str]:
        if not isinstance(request.get("method"), str) or not isinstance(request.get("url"), str):
            raise ValueError("Network evidence requires method and url")
        return run_id, request["method"], request["url"], request.get("phase", "during")

    for verdict in selected:
        for request in verdict["effect_diff"]["network"]:
            result.append(deepcopy(request))
            from_verdicts[key(verdict["run_id"], request)] += 1
    from_events: Counter[tuple[str, str, str, str]] = Counter()
    for event in trace.get("events", []):
        if event["kind"] != "network_request":
            continue
        if (scoped or runs) and event["seq"] not in seqs and event["run_id"] not in runs:
            continue
        request = {**event["data"], "phase": event["phase"]}
        identity = key(event["run_id"], request)
        from_events[identity] += 1
        if from_events[identity] > from_verdicts[identity]:
            result.append(deepcopy(request))
    return result
