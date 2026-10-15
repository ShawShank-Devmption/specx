"""Evaluate S6 on injected post-phase leaks and fresh benign runs."""

import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np

from specx.client.sandbox import SandboxClient
from specx.safety.s6.collect import TraceRun, load_app_records

LEAK_KINDS = ["delayed_post", "storage_write", "third_party_fetch", "background_poll"]
LEAK_DELAYS_MS = [300, 800, 1400]


@dataclass(frozen=True)
class EvaluationResult:
    injected: dict[str, list[TraceRun]]
    benign: list[TraceRun]


def _write_tool(tools: list[dict[str, Any]]) -> dict[str, Any]:
    write_tools = [tool for tool in tools if tool.get("risk_level") != "read"]
    verified = [tool for tool in write_tools if tool.get("status") == "verified"]
    fallback = [tool for tool in write_tools if tool.get("status") != "quarantined"]
    choices = verified or fallback
    if not choices:
        raise ValueError("S6 injection requires a verified or non-quarantined write tool")
    return choices[0]


def _evaluate_batch(
    *,
    app: str,
    kind: str | None,
    count: int,
    seed: int,
    client_factory: Callable[[], SandboxClient],
    post_observe_ms: int,
) -> list[TraceRun]:
    tools, contracts = load_app_records(app)
    tool = _write_tool(tools)
    rng = np.random.default_rng(seed)
    client = client_factory()
    session_id: str | None = None
    runs: list[TraceRun] = []
    try:
        session_id = client.create_session(app, seed=seed)
        client.load_tools(session_id, tools, contracts)
        for index in range(count):
            client.reset(session_id, seed=seed + index)
            if kind is not None:
                client.inject_leak(
                    session_id,
                    kind,
                    int(rng.choice(LEAK_DELAYS_MS)),
                )
            args = client.example_args(session_id, str(tool["tool_id"]))
            verdict = client.invoke(
                session_id,
                str(tool["tool_id"]),
                args,
                source="s6_inject" if kind is not None else "s6_approved",
                post_observe_ms=post_observe_ms,
            )
            events = [
                event for event in client.events(session_id) if event["run_id"] == verdict["run_id"]
            ]
            runs.append(TraceRun(app=app, verdict=verdict, events=events))
    finally:
        if session_id is not None:
            client.close(session_id)
        client.shutdown()
    return runs


def _chunks(total: int, max_workers: int) -> list[int]:
    if total == 0:
        return []
    chunk_size = max(1, math.ceil(total / max_workers))
    return [min(chunk_size, total - offset) for offset in range(0, total, chunk_size)]


def evaluate_leaks(
    apps: list[str],
    *,
    leaks_per_kind: int = 25,
    benign_runs: int = 100,
    seed: int = 0,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
    max_workers: int = 4,
    post_observe_ms: int = 2000,
) -> EvaluationResult:
    if leaks_per_kind < 0 or benign_runs < 0:
        raise ValueError("evaluation counts must be non-negative")
    if not apps:
        raise ValueError("at least one app is required")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")

    jobs: list[dict[str, Any]] = []
    job_number = 0
    for kind in [*LEAK_KINDS, None]:
        total = leaks_per_kind if kind is not None else benign_runs
        per_app, remainder = divmod(total, len(apps))
        for app_index, app in enumerate(apps):
            app_total = per_app + (1 if app_index < remainder else 0)
            for count in _chunks(app_total, max_workers):
                jobs.append(
                    {
                        "app": app,
                        "kind": kind,
                        "count": count,
                        "seed": seed + job_number * 1000,
                        "client_factory": client_factory,
                        "post_observe_ms": post_observe_ms,
                    }
                )
                job_number += 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        batches = list(executor.map(lambda kwargs: _evaluate_batch(**kwargs), jobs))
    injected: dict[str, list[TraceRun]] = {kind: [] for kind in LEAK_KINDS}
    benign: list[TraceRun] = []
    for job, batch in zip(jobs, batches, strict=True):
        kind = job["kind"]
        if kind is None:
            benign.extend(batch)
        else:
            injected[str(kind)].extend(batch)
    return EvaluationResult(injected=injected, benign=benign)
