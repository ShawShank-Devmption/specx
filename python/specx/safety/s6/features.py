"""Convert sandbox event streams into fixed-width S6 feature windows."""

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

WINDOW_MS = 250
FEATURES = [
    "n_req",
    "n_post_like",
    "n_unapproved",
    "n_third_party",
    "req_bytes",
    "n_resp",
    "resp_bytes",
    "n_dom_mut",
    "n_storage",
    "n_console",
    "n_nav",
    "n_audit",
    "is_post_phase",
    "ms_since_tool_end",
]


class RunWindows(BaseModel):
    run_id: str
    tool_id: str
    X: list[list[float]] = Field(min_length=1)


def _feature_row(window_start: float, tool_end: float) -> list[float]:
    row = [0.0] * len(FEATURES)
    row[FEATURES.index("is_post_phase")] = float(window_start >= tool_end)
    row[FEATURES.index("ms_since_tool_end")] = max(0.0, window_start - tool_end)
    return row


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("event data must be an object")
    return data


def windows_for_run(
    events: list[dict[str, Any]], *, window_ms: int = WINDOW_MS, horizon_ms: int = 2000
) -> RunWindows:
    if not events:
        raise ValueError("a run must contain at least one event")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    if horizon_ms < 0:
        raise ValueError("horizon_ms must be non-negative")

    ordered = sorted(events, key=lambda event: (event.get("seq", 0), event.get("t_ms", 0)))
    starts = [event for event in ordered if event.get("kind") == "tool_start"]
    ends = [event for event in ordered if event.get("kind") == "tool_end"]
    if not starts or not ends:
        raise ValueError("a run must contain tool_start and tool_end events")

    start = float(starts[0]["t_ms"])
    end = float(ends[-1]["t_ms"])
    if end < start:
        raise ValueError("tool_end cannot precede tool_start")

    stop = end + horizon_ms
    n_windows = math.floor((stop - start) / window_ms) + 1
    rows = [_feature_row(start + index * window_ms, end) for index in range(n_windows)]

    for event in ordered:
        t_ms = float(event["t_ms"])
        if t_ms < start or t_ms > stop:
            continue
        index = math.floor((t_ms - start) / window_ms)
        row = rows[index]
        kind = event.get("kind")
        data = _event_data(event)

        if kind == "network_request":
            row[0] += 1
            if str(data.get("method", "")).upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                row[1] += 1
            if data.get("approved") is False:
                row[2] += 1
            if data.get("third_party") is True:
                row[3] += 1
            row[4] += float(data.get("body_bytes", 0))
        elif kind == "network_response":
            row[5] += 1
            row[6] += float(data.get("body_bytes", 0))
        elif kind == "dom_mutation":
            row[7] += 1
        elif kind == "storage":
            row[8] += 1
        elif kind == "console":
            row[9] += 1
        elif kind == "navigation":
            row[10] += 1
        elif kind == "audit":
            row[11] += 1

    start_data = _event_data(starts[0])
    tool_id = start_data.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id:
        raise ValueError("tool_start must contain a non-empty tool_id")
    run_id = ordered[0].get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("events must contain a non-empty run_id")
    return RunWindows(run_id=run_id, tool_id=tool_id, X=rows)


def windows_from_jsonl(path: Path) -> list[RunWindows]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            run_id = event.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise ValueError(f"line {line_number} has no run_id")
            grouped[run_id].append(event)

    return [windows_for_run(events) for events in grouped.values()]


def to_sequences(runs: list[RunWindows], seq_len: int = 8) -> np.ndarray:
    if seq_len <= 0:
        raise ValueError("seq_len must be positive")
    sequences = np.zeros((len(runs), seq_len, len(FEATURES)), dtype=np.float32)
    for run_index, run in enumerate(runs):
        windows = np.asarray(run.X, dtype=np.float32)
        if windows.ndim != 2 or windows.shape[1] != len(FEATURES):
            raise ValueError(f"run {run.run_id} must have {len(FEATURES)} features per window")
        copied = min(seq_len, windows.shape[0])
        sequences[run_index, :copied] = windows[:copied]
    return sequences
