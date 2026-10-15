"""Seeded synthetic S6 runs derived from contract-valid event fixtures."""

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np

from specx.safety.s6.features import RunWindows, windows_for_run

LEAK_KINDS = {"delayed_post", "storage_write", "third_party_fetch", "background_poll"}


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _leak_events(
    kind: str, *, run_id: str, session_id: str, seq: int, t_ms: float
) -> list[dict[str, Any]]:
    common = {"session_id": session_id, "run_id": run_id, "phase": "post"}
    if kind == "storage_write":
        return [
            {
                **common,
                "seq": seq,
                "t_ms": t_ms,
                "kind": "storage",
                "data": {"area": "local", "op": "set", "key": "__trk"},
            }
        ]
    if kind in {"delayed_post", "third_party_fetch"}:
        third_party = kind == "third_party_fetch"
        url = (
            "https://tracker.example.invalid/p"
            if third_party
            else "http://127.0.0.1:5101/api/analytics"
        )
        return [
            {
                **common,
                "seq": seq,
                "t_ms": t_ms,
                "kind": "network_request",
                "data": {
                    "request_id": f"leak-{run_id}",
                    "method": "POST",
                    "url": url,
                    "host": "tracker.example.invalid" if third_party else "127.0.0.1:5101",
                    "third_party": third_party,
                    "approved": False,
                    "body_bytes": 310,
                    "initiator": "script",
                },
            }
        ]
    return [
        {
            **common,
            "seq": seq + offset,
            "t_ms": t_ms + offset * 80,
            "kind": "network_request",
            "data": {
                "request_id": f"poll-{run_id}-{offset}",
                "method": "GET",
                "url": "http://127.0.0.1:5101/api/cart",
                "host": "127.0.0.1:5101",
                "third_party": False,
                "approved": True,
                "body_bytes": 0,
                "initiator": "script",
            },
        }
        for offset in range(4)
    ]


def synthetic_runs(
    template_events: list[dict[str, Any]],
    *,
    n: int,
    seed: int,
    leak_kind: str | None = None,
) -> list[RunWindows]:
    if n < 0:
        raise ValueError("n must be non-negative")
    if leak_kind is not None and leak_kind not in LEAK_KINDS:
        raise ValueError(f"unknown leak kind: {leak_kind}")

    rng = np.random.default_rng(seed)
    runs: list[RunWindows] = []
    for index in range(n):
        events = copy.deepcopy(template_events)
        run_id = f"synthetic-{seed}-{index}"
        session_id = f"synthetic-session-{seed}-{index}"
        time_scale = float(rng.uniform(0.8, 1.2))
        for event in events:
            event["run_id"] = run_id
            event["session_id"] = session_id
            event["t_ms"] = round(float(event["t_ms"]) * time_scale, 3)
            data = event.get("data", {})
            if "body_bytes" in data:
                byte_scale = float(rng.uniform(0.7, 1.3))
                data["body_bytes"] = max(0, round(float(data["body_bytes"]) * byte_scale))

        if leak_kind is not None:
            tool_end = max(event["t_ms"] for event in events if event["kind"] == "tool_end")
            delay = float(rng.choice([300, 800, 1400]))
            events.extend(
                _leak_events(
                    leak_kind,
                    run_id=run_id,
                    session_id=session_id,
                    seq=max(int(event["seq"]) for event in events) + 1,
                    t_ms=tool_end + delay,
                )
            )
        runs.append(windows_for_run(events))
    return runs
