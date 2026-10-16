"""PPO training and outcome logging for the S1 adversarial fuzzer."""

from collections.abc import Callable
from typing import Any, cast

from gymnasium import Env
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from specx.safety.s1.baselines import EpisodeLog
from specx.safety.s1.env import SpecXFuzzEnv


class _EpisodeLogCallback(BaseCallback):
    def __init__(self, *, app: str, seed: int, total_steps: int) -> None:
        super().__init__(verbose=0)
        self.app = app
        self.seed = seed
        self.total_steps = total_steps
        self.signatures: set[str] = set()
        self.first_violation_step: int | None = None
        self.first_high_step: int | None = None
        self.verdict_run_ids: list[str] = []
        self.per_step_new: list[int] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        remaining = self.total_steps - len(self.per_step_new)
        for info in infos[:remaining]:
            step_number = len(self.per_step_new) + 1
            new = set(info.get("new_signatures", []))
            self.signatures.update(new)
            self.per_step_new.append(len(new))
            verdicts = info.get("verdicts", [])
            self.verdict_run_ids.extend(
                verdict["run_id"] for verdict in verdicts if isinstance(verdict.get("run_id"), str)
            )
            if new and self.first_violation_step is None:
                self.first_violation_step = step_number
            if self.first_high_step is None and any(
                violation.get("severity") == "high" and violation.get("signature") in new
                for verdict in verdicts
                for violation in verdict.get("violations", [])
            ):
                self.first_high_step = step_number
            if step_number % 100 == 0:
                print(
                    f"{self.app} ppo seed={self.seed} step={step_number} "
                    f"signatures={len(self.signatures)}",
                    flush=True,
                )
        return len(self.per_step_new) < self.total_steps

    def episode_log(self) -> EpisodeLog:
        return EpisodeLog(
            method="ppo",
            app=self.app,
            seed=self.seed,
            steps=len(self.per_step_new),
            signatures=sorted(self.signatures),
            first_violation_step=self.first_violation_step,
            first_high_step=self.first_high_step,
            verdict_run_ids=self.verdict_run_ids,
            per_step_new=self.per_step_new,
        )


def train_ppo(
    env_fns: list[Callable[[], SpecXFuzzEnv]], *, total_steps: int, seed: int
) -> tuple[PPO, EpisodeLog]:
    if not env_fns:
        raise ValueError("at least one environment factory is required")
    if total_steps <= 0:
        raise ValueError("total_steps must be positive")

    generic_env_fns = [cast(Callable[[], Env[Any, Any]], env_fn) for env_fn in env_fns]
    vec_env = DummyVecEnv(generic_env_fns)
    first_env: Any = vec_env.envs[0]
    callback = _EpisodeLogCallback(app=str(first_env.app), seed=seed, total_steps=total_steps)
    model = PPO(
        "MlpPolicy",
        vec_env,
        n_steps=64,
        batch_size=64,
        n_epochs=4,
        learning_rate=3e-4,
        ent_coef=0.02,
        gamma=0.95,
        seed=seed,
        verbose=0,
        device="cpu",
    )
    try:
        model.learn(total_timesteps=total_steps, callback=callback)
    finally:
        vec_env.close()
    return model, callback.episode_log()
