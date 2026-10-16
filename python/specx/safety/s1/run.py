"""Run S1 random, coverage-guided, and PPO fuzzers against the sandbox."""

import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import typer

from specx.client.io import read_jsonl, write_json
from specx.client.paths import repo_root, verdicts_path
from specx.client.sandbox import SandboxClient
from specx.client.seeding import seed_everything
from specx.safety.s1.baselines import EpisodeLog, run_coverage_greedy, run_random
from specx.safety.s1.env import SpecXFuzzEnv
from specx.safety.s1.metrics import metrics
from specx.safety.s1.train import train_ppo
from specx.safety.s6.collect import load_app_records

PPO_HYPERPARAMETERS: dict[str, Any] = {
    "policy": "MlpPolicy",
    "n_envs": 4,
    "n_steps": 64,
    "batch_size": 64,
    "n_epochs": 4,
    "learning_rate": 3e-4,
    "ent_coef": 0.02,
    "gamma": 0.95,
}


def _resolve_out(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_log(output: Path, log: EpisodeLog) -> None:
    write_json(output / "logs" / f"{log.app}-{log.method}-seed{log.seed}.json", log.model_dump())


def _verdicts_for_methods() -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for source in ("s1_random", "s1_coverage", "s1"):
        path = verdicts_path(source)
        if path.exists():
            verdicts.extend(read_jsonl(path))
    return verdicts


def _baseline_job(
    app: str,
    method: str,
    seed: int,
    steps: int,
    post_observe_ms: int,
    client_factory: Callable[[], SandboxClient],
) -> EpisodeLog:
    tools, contracts = load_app_records(app)
    env = SpecXFuzzEnv(
        client_factory(),
        app,
        tools,
        contracts,
        source=f"s1_{method}",
        horizon=25,
        post_observe_ms=post_observe_ms,
        seed=seed,
    )
    rng = np.random.default_rng(seed)
    if method == "random":
        return run_random(env, steps, rng)
    if method == "coverage":
        return run_coverage_greedy(env, steps, rng)
    raise ValueError(f"unknown baseline method: {method}")


def run_experiment(
    apps: list[str],
    *,
    steps: int,
    seeds: int,
    out: Path,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
    ppo_envs: int = 4,
    baseline_workers: int = 4,
    post_observe_ms: int = 300,
    max_seconds: float = 90 * 60,
) -> dict[str, Any]:
    if not apps:
        raise ValueError("at least one app is required")
    if steps <= 0 or seeds <= 0 or ppo_envs <= 0 or baseline_workers <= 0:
        raise ValueError("steps, seeds, ppo_envs, and baseline_workers must be positive")
    if max_seconds <= 0:
        raise ValueError("max_seconds must be positive")

    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    output = _resolve_out(out)
    output.mkdir(parents=True, exist_ok=True)
    seed_everything(0)
    logs: list[EpisodeLog] = []
    seeds_completed = 0

    for seed in range(seeds):
        baseline_jobs = [
            (app, method, seed, steps, post_observe_ms, client_factory)
            for app in apps
            for method in ("random", "coverage")
        ]
        with ThreadPoolExecutor(max_workers=baseline_workers) as executor:
            baseline_logs = list(executor.map(lambda args: _baseline_job(*args), baseline_jobs))
        for log in baseline_logs:
            logs.append(log)
            _write_log(output, log)

        for app in apps:
            tools, contracts = load_app_records(app)

            def make_env(
                source: str,
                *,
                env_seed: int = seed,
                app_name: str = app,
                app_tools: list[dict[str, Any]] = tools,
                app_contracts: list[dict[str, Any]] = contracts,
            ) -> SpecXFuzzEnv:
                return SpecXFuzzEnv(
                    client_factory(),
                    app_name,
                    app_tools,
                    app_contracts,
                    source=source,
                    horizon=25,
                    post_observe_ms=post_observe_ms,
                    seed=env_seed,
                )

            env_fns = [lambda: make_env("s1") for _ in range(ppo_envs)]
            model, ppo_log = train_ppo(env_fns, total_steps=steps, seed=seed)
            logs.append(ppo_log)
            _write_log(output, ppo_log)
            checkpoint = output / "ckpt" / f"{app}-seed{seed}"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            model.save(checkpoint)

        seeds_completed += 1
        if time.perf_counter() - started_clock >= max_seconds:
            break

    result = metrics(logs, verdicts=_verdicts_for_methods())
    result["seeds_completed"] = seeds_completed
    write_json(output / "metrics.json", result)
    finished_at = datetime.now(UTC)
    write_json(
        output / "run.json",
        {
            "git_sha": _git_sha(),
            "args": {
                "apps": apps,
                "steps": steps,
                "seeds": seeds,
                "out": str(output),
                "post_observe_ms": post_observe_ms,
                "max_seconds": max_seconds,
                "baseline_workers": baseline_workers,
            },
            "ppo_hyperparameters_tried": [{**PPO_HYPERPARAMETERS, "n_envs": ppo_envs}],
            "seeds_completed": seeds_completed,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
        },
    )
    return result


def main(
    apps: Annotated[str, typer.Option("--apps")] = "shop,admin",
    steps: Annotated[int, typer.Option("--steps")] = 1500,
    seeds: Annotated[int, typer.Option("--seeds")] = 3,
    out: Annotated[Path, typer.Option("--out")] = Path("results/s1"),
) -> None:
    run_experiment(
        [app.strip() for app in apps.split(",") if app.strip()],
        steps=steps,
        seeds=seeds,
        out=out,
    )


if __name__ == "__main__":
    typer.run(main)
