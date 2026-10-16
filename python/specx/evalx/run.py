"""Resumable benchmark CLI and orchestration over the frozen episode harness.

Published JSONL/traces live under SPECX_RESULTS_DIR; --out selects the directory for
run.json and metrics.json. No fake trials or missing-stage stand-ins are emitted by CLI.
"""

import json
import random
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import typer
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from specx.client import SandboxClient
from specx.client.io import read_json
from specx.client.paths import contracts_path, repo_root, stage_dir
from specx.client.schemas import validate
from specx.client.seeding import seed_everything
from specx.evalx.benchmark_pool import check_sandbox, execute_jobs
from specx.evalx.benchmark_store import TrialJob, TrialStore, atomic_json
from specx.evalx.conditions import Condition, tool_set_for
from specx.evalx.llm import AgentLLM, AnthropicLLM
from specx.evalx.selection import OptimisationSelection, select_optimised, verified_tools
from specx.evalx.tasks import load_tasks
from specx.stats.paired import summarize

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


class RunRecord(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    status: Literal["running", "complete", "failed"]
    git_sha: str
    git_dirty: bool
    started_at: str
    finished_at: str | None = None
    args: dict[str, Any]
    models: dict[str, str]
    execution: str
    requested: int
    skipped: int
    completed: int = 0
    trial_order: list[str]
    estimated_spend_usd: float = Field(default=0, ge=0)
    cumulative_episodes: int = Field(default=0, ge=0)
    error: str | None = None
    optimisation_selection: dict[str, OptimisationSelection] = Field(default_factory=dict)


def _jobs(
    apps: list[str],
    conditions: list[Condition],
    trials: int,
    seed: int,
    split: str,
    task_ids: list[str] | None,
    arm: str | None,
    selected_tools: dict[str, list[dict[str, Any]]] | None = None,
    selections: dict[str, OptimisationSelection] | None = None,
) -> list[TrialJob]:
    jobs: list[TrialJob] = []
    found: set[str] = set()
    requested = set(task_ids or [])
    for name in sorted(apps):
        tasks = [
            task
            for task in load_tasks(name)
            if task.split == split and (not requested or task.task_id in requested)
        ]
        found.update(task.task_id for task in tasks)
        if not tasks:
            raise ValueError(f"No {split} tasks selected for app {name}")
        for condition in sorted(conditions, key=lambda item: item.value):
            if condition == Condition.optimised and selected_tools is not None:
                tools = selected_tools[name]
            elif condition == Condition.verified:
                tools = verified_tools(name)
            else:
                tools, _ = tool_set_for(name, condition, arm)
            contracts = None
            if condition != Condition.raw_dom:
                contracts = read_json(contracts_path(name))
                if not isinstance(contracts, list):
                    raise ValueError(f"Expected contract array for {name}")
                for contract in contracts:
                    validate("contract", contract)
                contract_tool_ids = {contract["tool_id"] for contract in contracts}
                tools = [tool for tool in tools if tool["tool_id"] in contract_tool_ids]
            jobs.extend(
                TrialJob(
                    task=task,
                    condition=condition,
                    seed=trial_seed,
                    tools=tools,
                    contracts=contracts,
                    optimisation_selection=(
                        selections[name].model_dump(mode="json")
                        if selections and condition == Condition.optimised
                        else None
                    ),
                )
                for task in sorted(tasks, key=lambda item: item.task_id)
                for trial_seed in range(seed, seed + trials)
            )
    if requested - found:
        raise ValueError(f"Unknown or wrong-split task IDs: {sorted(requested - found)}")
    random.Random(seed).shuffle(jobs)
    return jobs


def _metrics(jobs: list[TrialJob], store: TrialStore, execution: str) -> dict[str, Any]:
    conditions = sorted({job.condition for job in jobs}, key=lambda item: item.value)
    by_condition = {condition: store.records(condition) for condition in conditions}
    result: dict[str, Any] = {}
    completed = 0
    for condition in conditions:
        result[condition.value] = {}
        for name in sorted({job.task.app for job in jobs if job.condition == condition}):
            rows = [
                by_condition[condition][job.trial_id]
                for job in jobs
                if job.task.app == name
                and job.condition == condition
                and job.trial_id in by_condition[condition]
            ]
            completed += len(rows)
            result[condition.value][name] = summarize(rows)
    return {
        "conditions": result,
        "requested": len(jobs),
        "completed": completed,
        "complete": completed == len(jobs),
        "execution": execution,
    }


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root(), capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("Cannot identify the repository revision")
    return result.stdout.strip()


def _git_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def run_benchmark(
    *,
    apps: list[str],
    conditions: list[Condition],
    trials: int = 5,
    seed: int = 0,
    split: str = "heldout",
    workers: int = 8,
    max_steps: int = 40,
    task_ids: list[str] | None = None,
    arm: str | None = None,
    optimisation_dir: Path | None = None,
    out: Path | None = None,
    llm: AgentLLM,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
) -> dict[str, Any]:
    """Run a requested cohort; resume only schema-valid, context-matching episodes.

    Inject a client/model for offline tests. Real callers share one AnthropicLLM across
    workers so model identity, budget and cumulative spend remain shared.
    """
    if (
        not apps
        or len(set(apps)) != len(apps)
        or not conditions
        or len(set(conditions)) != len(conditions)
    ):
        raise ValueError("apps and conditions must be non-empty and unique")
    if trials < 1 or seed < 0 or not 1 <= workers <= 8 or not 1 <= max_steps <= 40:
        raise ValueError("Require trials >= 1, seed >= 0, workers 1..8 and max_steps 1..40")
    if split not in ("train", "heldout"):
        raise ValueError("split must be train or heldout")
    conditions = [Condition(condition) for condition in conditions]
    seed_everything(seed)
    output = (
        (out if out.is_absolute() else repo_root() / out).resolve()
        if out is not None
        else stage_dir("evalx")
    )
    execution = (
        "real"
        if client_factory is SandboxClient and isinstance(llm, AnthropicLLM)
        else "test_double"
    )
    selections: dict[str, OptimisationSelection] = {}
    selected_tools: dict[str, list[dict[str, Any]]] = {}
    store = TrialStore()
    with store.writer():
        # The optimisation writer shares this lock: select one stable snapshot.
        if Condition.optimised in conditions:
            for name in apps:
                selected_tools[name], selections[name] = select_optimised(
                    name,
                    model=llm.model,
                    execution=execution,
                    arm=arm,
                    optimisation_dir=optimisation_dir,
                )
        jobs = _jobs(
            apps,
            conditions,
            trials,
            seed,
            split,
            task_ids,
            arm,
            selected_tools if selections else None,
            selections,
        )
        existing = {condition: store.records(condition) for condition in conditions}
        pending = []
        for job in jobs:
            record = existing[job.condition].get(job.trial_id)
            if record is None:
                pending.append(job)
            else:
                store.check_completed(job, record, llm.model, max_steps)
        previous_path = output / "run.json"
        if previous_path.exists():
            previous = RunRecord.model_validate(read_json(previous_path))
            if previous.optimisation_selection and previous.optimisation_selection != selections:
                raise ValueError("Resume optimisation selection context mismatch in run.json")
            if isinstance(llm, AnthropicLLM) and previous.models["agent"] != llm.model:
                raise ValueError("Resume model context mismatch in run.json")
            if isinstance(llm, AnthropicLLM):
                llm.spent_usd = max(llm.spent_usd, previous.estimated_spend_usd)
                llm.episodes = max(llm.episodes, previous.cumulative_episodes)
        run = RunRecord(
            status="running",
            git_sha=_git_sha(),
            git_dirty=_git_dirty(),
            started_at=datetime.now(UTC).isoformat(),
            args={
                "apps": apps,
                "conditions": [condition.value for condition in conditions],
                "trials": trials,
                "seed": seed,
                "split": split,
                "workers": workers,
                "max_steps": max_steps,
                "task_ids": task_ids,
                "arm": arm,
                "optimisation_dir": str(optimisation_dir) if optimisation_dir is not None else None,
            },
            models={"agent": llm.model},
            execution=execution,
            requested=len(jobs),
            skipped=len(jobs) - len(pending),
            trial_order=[job.trial_id for job in jobs],
            optimisation_selection=selections,
        )
        atomic_json(output / "run.json", run.model_dump())
        try:
            if pending:
                check_sandbox(client_factory, apps)
                execute_jobs(
                    pending,
                    workers=workers,
                    max_steps=max_steps,
                    llm=llm,
                    store=store,
                    client_factory=client_factory,
                )
            run.status = "complete"
        except BaseException as error:
            run.status, run.error = "failed", f"{type(error).__name__}: {error}"
            raise
        finally:
            run.finished_at = datetime.now(UTC).isoformat()
            run.completed = store.completed
            run.estimated_spend_usd = getattr(llm, "spent_usd", 0.0)
            run.cumulative_episodes = getattr(llm, "episodes", 0)
            atomic_json(output / "run.json", run.model_dump())
            metrics = _metrics(jobs, store, execution)
            if selections:
                metrics["optimisation_selection"] = {
                    name: choice.model_dump(mode="json") for name, choice in selections.items()
                }
                metrics["notes"] = [choice.note for choice in selections.values()]
            atomic_json(output / "metrics.json", metrics)
    return metrics


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@app.command()
def main(
    conditions: str = "raw_dom",
    apps: str = "shop,admin",
    trials: int = typer.Option(5, min=1),
    seed: int = typer.Option(0, min=0),
    split: str = "heldout",
    workers: int = typer.Option(8, min=1, max=8),
    max_steps: int = typer.Option(40, min=1, max=40),
    task_ids: str = "",
    arm: str | None = None,
    optimisation_dir: Path | None = None,
    out: Path | None = None,
) -> None:
    """Run paired benchmark trials against live seed apps and sandbox HTTP."""
    import os

    load_dotenv(repo_root() / ".env", override=False)
    try:
        parsed = [Condition(name) for name in _csv(conditions)]
        if (
            not os.environ.get("ANTHROPIC_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-..."
        ):
            raise ValueError(
                "Configure ANTHROPIC_API_KEY in .env or the environment before live trials"
            )
        llm = AnthropicLLM()
        try:
            metrics = run_benchmark(
                apps=_csv(apps),
                conditions=parsed,
                trials=trials,
                seed=seed,
                split=split,
                workers=workers,
                max_steps=max_steps,
                task_ids=_csv(task_ids) or None,
                arm=arm,
                optimisation_dir=optimisation_dir,
                out=out,
                llm=llm,
            )
        finally:
            llm.close()
    except Exception as error:
        typer.echo(f"Benchmark failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    app()
