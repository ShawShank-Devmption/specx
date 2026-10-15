"""Training-only F2 optimisation with per-candidate traces and auditable gate logs.

Runs are deliberately non-resumable: refuse existing app/arm runs rather than mix
different baselines. Use a fresh SPECX_RESULTS_DIR for a new experiment.
"""

import json
import os
import subprocess
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

from specx.client import SandboxClient
from specx.client.io import append_jsonl, read_json
from specx.client.paths import (
    contracts_path,
    patches_dir,
    repo_root,
    stage_dir,
    tools_path,
    traces_dir,
    trials_path,
)
from specx.client.seeding import seed_everything
from specx.evalx.agent import run_episode
from specx.evalx.benchmark_pool import check_sandbox
from specx.evalx.benchmark_store import TrialStore, atomic_json
from specx.evalx.conditions import Condition, select_tools
from specx.evalx.llm import AgentLLM, AnthropicLLM
from specx.evalx.tasks import Task, load_tasks
from specx.optim.budget import BudgetedLLM
from specx.optim.bundles import harvest, synthetic_failures
from specx.optim.dataset import export_accepted
from specx.optim.gate import gate
from specx.optim.patch import apply_patch
from specx.optim.reviser import Arm, propose
from specx.stats.paired import summarize

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


def _evaluate(
    name: str,
    tools: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    tasks: list[Task],
    *,
    trials: int,
    seed: int,
    max_steps: int,
    llm: AgentLLM,
    client_factory: Callable[[], SandboxClient],
) -> tuple[list[dict[str, Any]], Path]:
    path = trials_path(name)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite trials: {path}")
    records = []
    with client_factory() as client:
        session = client.create_session(tasks[0].app, seed=seed)
        try:
            for task in tasks:
                for trial_seed in range(seed, seed + trials):
                    trial_id = f"{name}.{task.task_id}.s{trial_seed}"
                    trial, trace = run_episode(
                        client,
                        task.app,
                        task,
                        Condition.optimised,
                        trial_seed,
                        tools=tools,
                        contracts=contracts,
                        llm=llm,
                        max_steps=max_steps,
                        session_id=session,
                        trial_id=trial_id,
                        revision_id=name,
                    )
                    trace["task"] = task.model_dump(exclude_none=True)
                    trace_path = traces_dir() / f"{trial_id}.json"
                    trial["trace_path"] = str(trace_path)
                    atomic_json(trace_path, trace)
                    append_jsonl(path, trial)
                    records.append(trial)
        finally:
            client.close(session)
    return records, path


def _optimise_arm(
    name: str,
    arm: Arm,
    initial: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    baseline_path: Path,
    evaluate: Callable[..., tuple[list[dict[str, Any]], Path]],
    reviser: AgentLLM,
    max_iters: int,
    seed: int,
) -> dict[str, Any]:
    tools, before, evidence_path = deepcopy(initial), baseline, baseline_path
    metrics: dict[str, Any] = {
        "success_by_iter": [summarize(before)["success_rate"]],
        "iterations_to_convergence": 0,
        "proposed": 0,
        "accepted": 0,
        "rejected": {"no_improvement": 0, "safety_regression": 0, "insufficient_n": 0},
        "revisions": [],
        "stop_reason": "max_iters",
    }
    for iteration in range(1, max_iters + 1):
        bundles = harvest(evidence_path, traces_dir(), tools, split="train")
        if not bundles:
            metrics["stop_reason"] = "no_failures"
            break
        if len(bundles) < 3:
            bundles += synthetic_failures(tools, n=3 - len(bundles), seed=seed + iteration)
        ids = sorted({identity for bundle in bundles for identity in bundle.tool_ids})
        accepted = 0
        for index, identity in enumerate(ids):
            tool = next(tool for tool in tools if tool["tool_id"] == identity)
            evidence = [bundle for bundle in bundles if identity in bundle.tool_ids]
            # If another tool was accepted, collect fresh evidence for this candidate.
            if accepted:
                fresh = harvest(evidence_path, traces_dir(), tools, split="train")
                evidence = [bundle for bundle in fresh if identity in bundle.tool_ids]
                if not evidence:
                    continue
            patch = propose(arm, evidence, tool, llm=reviser)
            candidate = [
                apply_patch(item, patch) if item["tool_id"] == identity else deepcopy(item)
                for item in tools
            ]
            candidate = select_tools(name, candidate, Condition.optimised)
            atomic_json(
                patches_dir() / f"{name}.{arm.value}.{iteration}.{identity}.patch.json", patch
            )
            metrics["proposed"] += 1
            after, candidate_path = evaluate(
                f"gate_{name}_{arm.value}_{iteration}_c{index}", candidate
            )
            decision = gate(before, after)
            log = {
                "app": name,
                "arm": arm.value,
                "iter": iteration,
                "tool_id": identity,
                "patch_id": patch["patch_id"],
                "trials_path": str(candidate_path),
                **decision.model_dump(mode="json"),
            }
            append_jsonl(stage_dir("f2") / "revisions.jsonl", log)
            metrics["revisions"].append(log)
            if decision.accepted:
                tools, before, evidence_path = candidate, after, candidate_path
                accepted += 1
                metrics["accepted"] += 1
                export_accepted(evidence, patch, arm.value)
            else:
                metrics["rejected"][decision.reason] += 1
        metrics["iterations_to_convergence"] = iteration
        metrics["success_by_iter"].append(summarize(before)["success_rate"])
        if not accepted:
            metrics["stop_reason"] = "no_accepted_patch"
            break
    atomic_json(tools_path(name, f"optimised.{arm.value}"), tools)
    return metrics


def run_optimisation(
    *,
    apps: list[str],
    arms: list[Arm],
    llm: AgentLLM,
    reviser: AgentLLM,
    trials: int = 5,
    seed: int = 0,
    max_iters: int = 4,
    max_steps: int = 40,
    task_ids: list[str] | None = None,
    out: Path | None = None,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
) -> dict[str, Any]:
    if not apps or len(set(apps)) != len(apps) or not set(apps) <= {"shop", "admin"}:
        raise ValueError("Select unique supported apps")
    arms = [Arm(arm) for arm in arms]
    if not arms or len(set(arms)) != len(arms):
        raise ValueError("Select unique supported reviser arms")
    if trials < 1 or seed < 0 or max_iters < 1 or not 1 <= max_steps <= 40:
        raise ValueError("Invalid trials, seed, max_iters or max_steps")
    seed_everything(seed)
    output = out or stage_dir("f2")
    prepared = []
    for name in apps:
        tools = select_tools(name, read_json(tools_path(name)), Condition.verified)
        if not tools or any(tool["metadata_revision"] != 0 for tool in tools):
            raise ValueError("Optimisation requires a nonempty verified revision-zero tool set")
        tasks = [
            task
            for task in load_tasks(name)
            if task.split == "train" and (task_ids is None or task.task_id in task_ids)
        ]
        if not tasks:
            raise ValueError(f"No selected training tasks for {name}")
        prepared.append((name, tools, read_json(contracts_path(name)), tasks))
    found = {task.task_id for _, _, _, tasks in prepared for task in tasks}
    if task_ids is not None and set(task_ids) != found:
        raise ValueError("Unknown or held-out task selection")
    run_path = output / "run.json"
    with TrialStore().writer():
        if run_path.exists():
            raise FileExistsError(
                "Use a fresh output/results directory; optimisation does not resume"
            )
        check_sandbox(client_factory, apps)
        run: dict[str, Any] = {
            "status": "running",
            "git_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo_root(), text=True
            ).strip(),
            "git_dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=repo_root(), text=True
                ).strip()
            ),
            "started_at": datetime.now(UTC).isoformat(),
            "models": {"agent": llm.model, "reviser": reviser.model},
            "execution": "real"
            if client_factory is SandboxClient
            and isinstance(llm, AnthropicLLM)
            and isinstance(reviser, AnthropicLLM)
            else "test_double",
            "args": {
                "apps": apps,
                "arms": [arm.value for arm in arms],
                "trials": trials,
                "seed": seed,
                "max_iters": max_iters,
                "max_steps": max_steps,
                "task_ids": task_ids,
            },
        }
        atomic_json(run_path, run)
        metrics: dict[str, Any] = {"execution": run["execution"], "apps": {}}
        peers = (llm, reviser) if llm is not reviser else (llm,)
        try:
            llm, reviser = BudgetedLLM(llm, peers), BudgetedLLM(reviser, peers)
            for name, tools, contracts, tasks in prepared:
                evaluate = partial(
                    _evaluate,
                    contracts=contracts,
                    tasks=tasks,
                    trials=trials,
                    seed=seed,
                    max_steps=max_steps,
                    llm=llm,
                    client_factory=client_factory,
                )

                baseline, baseline_path = evaluate(f"gate_{name}_baseline", tools)
                metrics["apps"][name] = {}
                for arm in arms:
                    metrics["apps"][name][arm.value] = _optimise_arm(
                        name,
                        arm,
                        tools,
                        baseline,
                        baseline_path,
                        evaluate,
                        reviser,
                        max_iters,
                        seed,
                    )
                    atomic_json(output / "metrics.json", metrics)
            run["status"] = "complete"
        except BaseException as error:
            run.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            run["finished_at"] = datetime.now(UTC).isoformat()
            run["estimated_spend_usd"] = sum(getattr(model, "spent_usd", 0.0) for model in peers)
            atomic_json(run_path, run)
            atomic_json(output / "metrics.json", metrics)
    return metrics


@app.command()
def main(
    apps: str = "shop,admin",
    arms: str = "text_trace",
    max_iters: int = typer.Option(4, min=1),
    trials: int = typer.Option(5, min=1),
    seed: int = typer.Option(0, min=0),
    out: Path | None = None,
) -> None:
    """Optimise verified tools using training tasks only (requires live prerequisites)."""
    load_dotenv(repo_root() / ".env", override=False)
    try:
        if (
            not os.environ.get("ANTHROPIC_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-..."
        ):
            raise ValueError("Configure ANTHROPIC_API_KEY before live optimisation")
        model = os.environ.get("SPECX_GEN_MODEL", "").strip()
        if not model:
            raise ValueError("Configure SPECX_GEN_MODEL for the reviser")
        agent_llm = AnthropicLLM()
        reviser_llm = AnthropicLLM(model=model)
        try:
            metrics = run_optimisation(
                apps=apps.split(","),
                arms=[Arm(arm) for arm in arms.split(",")],
                llm=agent_llm,
                reviser=reviser_llm,
                trials=trials,
                seed=seed,
                max_iters=max_iters,
                out=out,
            )
        finally:
            agent_llm.close()
            reviser_llm.close()
    except Exception as error:
        typer.echo(f"Optimisation failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    app()
