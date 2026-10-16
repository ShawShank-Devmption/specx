"""Random and coverage-greedy baselines for the S1 fuzzing environment."""

from typing import Literal

import numpy as np
from pydantic import BaseModel

from specx.safety.s1.env import SpecXFuzzEnv


class EpisodeLog(BaseModel):
    method: str
    app: str
    seed: int
    steps: int
    signatures: list[str]
    first_violation_step: int | None
    first_high_step: int | None
    verdict_run_ids: list[str]
    per_step_new: list[int]


def _run(
    env: SpecXFuzzEnv,
    n_steps: int,
    rng: np.random.Generator,
    method: Literal["random", "coverage"],
) -> EpisodeLog:
    if n_steps < 0:
        raise ValueError("n_steps must be non-negative")
    env.reset(seed=env.seed_value)
    tries = np.zeros(env.n_actions, dtype=np.int64)
    signatures: set[str] = set()
    first_violation: int | None = None
    first_high: int | None = None
    run_ids: list[str] = []
    per_step_new: list[int] = []

    for step_number in range(1, n_steps + 1):
        if method == "random" or rng.random() < 0.2:
            action = int(rng.integers(env.n_actions))
        else:
            least = np.flatnonzero(tries == tries.min())
            action = int(least[int(rng.integers(len(least)))])
        tries[action] += 1
        _, _, terminated, truncated, info = env.step(action)
        new = set(info["new_signatures"])
        signatures.update(new)
        per_step_new.append(len(new))
        verdicts = info["verdicts"]
        run_ids.extend(
            verdict["run_id"] for verdict in verdicts if isinstance(verdict.get("run_id"), str)
        )
        if new and first_violation is None:
            first_violation = step_number
        if first_high is None and any(
            violation.get("severity") == "high" and violation.get("signature") in new
            for verdict in verdicts
            for violation in verdict.get("violations", [])
        ):
            first_high = step_number
        if terminated or truncated:
            env.reset()
        if step_number % 100 == 0:
            print(
                f"{env.app} {method} seed={env.seed_value} step={step_number} "
                f"signatures={len(signatures)}",
                flush=True,
            )

    env.close()
    return EpisodeLog(
        method=method,
        app=env.app,
        seed=env.seed_value,
        steps=n_steps,
        signatures=sorted(signatures),
        first_violation_step=first_violation,
        first_high_step=first_high,
        verdict_run_ids=run_ids,
        per_step_new=per_step_new,
    )


def run_random(env: SpecXFuzzEnv, n_steps: int, rng: np.random.Generator) -> EpisodeLog:
    return _run(env, n_steps, rng, "random")


def run_coverage_greedy(env: SpecXFuzzEnv, n_steps: int, rng: np.random.Generator) -> EpisodeLog:
    return _run(env, n_steps, rng, "coverage")
