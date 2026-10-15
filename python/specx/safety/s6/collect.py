"""Collect approved sandbox traces for training the S6 anomaly models."""

import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from specx.client.io import read_json
from specx.client.paths import contracts_path, repo_root, tools_path
from specx.client.sandbox import SandboxClient
from specx.client.schemas import validate


@dataclass(frozen=True)
class TraceRun:
    app: str
    verdict: dict[str, Any]
    events: list[dict[str, Any]]


@dataclass(frozen=True)
class CollectionResult:
    runs: list[TraceRun]
    n_attempted: int
    n_excluded: int


def load_app_records(app: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    published_tools = tools_path(app)
    published_contracts = contracts_path(app)
    using_fixtures = not (published_tools.exists() and published_contracts.exists())
    if not using_fixtures:
        tool_file, contract_file = published_tools, published_contracts
    else:
        tool_file = repo_root() / "fixtures" / "tools" / f"{app}.tools.json"
        contract_file = repo_root() / "fixtures" / "contracts" / f"{app}.contracts.json"
    if not tool_file.exists() or not contract_file.exists():
        raise FileNotFoundError(
            f"no tools/contracts for {app}; run the generate stage before S6 collection"
        )
    tools = read_json(tool_file)
    contracts = read_json(contract_file)
    if not isinstance(tools, list) or not isinstance(contracts, list):
        raise ValueError(f"tools and contracts for {app} must be arrays")
    if using_fixtures:
        contract_tool_ids = {contract["tool_id"] for contract in contracts}
        tools = [tool for tool in tools if tool["tool_id"] in contract_tool_ids]
    for tool in tools:
        validate("tool_definition", tool)
    for contract in contracts:
        validate("contract", contract)
    return tools, contracts


def _collect_tool(
    *,
    app: str,
    tool: dict[str, Any],
    tools: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    runs_per_tool: int,
    seed: int,
    client_factory: Callable[[], SandboxClient],
    post_observe_ms: int,
) -> CollectionResult:
    client = client_factory()
    session_id: str | None = None
    collected: list[TraceRun] = []
    excluded = 0
    try:
        session_id = client.create_session(app, seed=seed)
        client.load_tools(session_id, tools, contracts)
        for run_index in range(runs_per_tool):
            if run_index % 5 == 0:
                client.reset(session_id, seed=seed + run_index)
            args = client.example_args(session_id, str(tool["tool_id"]))
            verdict = client.invoke(
                session_id,
                str(tool["tool_id"]),
                args,
                source="s6_approved",
                post_observe_ms=post_observe_ms,
            )
            events = [
                event for event in client.events(session_id) if event["run_id"] == verdict["run_id"]
            ]
            if verdict["violations"]:
                excluded += 1
                continue
            collected.append(TraceRun(app=app, verdict=verdict, events=events))
    finally:
        if session_id is not None:
            client.close(session_id)
        client.shutdown()
    return CollectionResult(
        runs=collected,
        n_attempted=runs_per_tool,
        n_excluded=excluded,
    )


def collect_approved(
    apps: list[str],
    *,
    runs_per_tool: int = 20,
    min_runs: int = 0,
    seed: int = 0,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
    max_workers: int = 4,
    post_observe_ms: int = 2000,
) -> CollectionResult:
    if runs_per_tool <= 0:
        raise ValueError("runs_per_tool must be positive")
    if min_runs < 0:
        raise ValueError("min_runs must be non-negative")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")

    app_records: list[
        tuple[int, str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
    ] = []
    eligible_count = 0
    for app_index, app in enumerate(apps):
        tools, contracts = load_app_records(app)
        eligible = [tool for tool in tools if tool.get("status") != "quarantined"]
        app_records.append((app_index, app, tools, contracts, eligible))
        eligible_count += len(eligible)

    effective_runs_per_tool = runs_per_tool
    if min_runs and eligible_count:
        effective_runs_per_tool = max(runs_per_tool, math.ceil(min_runs / eligible_count))

    if min_runs and not eligible_count:
        raise RuntimeError("S6 collection found no eligible tools")

    results: list[CollectionResult] = []
    round_number = 0
    next_runs_per_tool = effective_runs_per_tool
    while True:
        jobs: list[dict[str, Any]] = []
        for app_index, app, tools, contracts, eligible in app_records:
            for tool_index, tool in enumerate(eligible):
                jobs.append(
                    {
                        "app": app,
                        "tool": tool,
                        "tools": tools,
                        "contracts": contracts,
                        "runs_per_tool": next_runs_per_tool,
                        "seed": (
                            seed + round_number * 1_000_000 + app_index * 10_000 + tool_index * 100
                        ),
                        "client_factory": client_factory,
                        "post_observe_ms": post_observe_ms,
                    }
                )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            round_results = list(executor.map(lambda kwargs: _collect_tool(**kwargs), jobs))
        results.extend(round_results)

        accepted = sum(len(result.runs) for result in results)
        if accepted >= min_runs or min_runs == 0:
            break
        accepted_this_round = sum(len(result.runs) for result in round_results)
        if accepted_this_round == 0:
            raise RuntimeError("S6 collection could not produce approved runs")
        round_number += 1
        next_runs_per_tool = math.ceil((min_runs - accepted) / eligible_count)

    return CollectionResult(
        runs=[run for result in results for run in result.runs],
        n_attempted=sum(result.n_attempted for result in results),
        n_excluded=sum(result.n_excluded for result in results),
    )
