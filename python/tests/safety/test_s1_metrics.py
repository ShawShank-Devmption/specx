from pathlib import Path

import numpy as np
import pytest

from specx.client.fake import FakeSandbox
from specx.client.paths import verdicts_path
from specx.safety.s1.baselines import EpisodeLog
from specx.safety.s1.env import SpecXFuzzEnv
from specx.safety.s1.metrics import metrics
from specx.safety.s1.train import train_ppo
from specx.safety.s6.collect import load_app_records


def _log(
    method: str,
    seed: int,
    *,
    steps: int,
    signatures: list[str],
    first_violation: int | None,
    first_high: int | None,
    run_ids: list[str],
) -> EpisodeLog:
    return EpisodeLog(
        method=method,
        app="shop",
        seed=seed,
        steps=steps,
        signatures=signatures,
        first_violation_step=first_violation,
        first_high_step=first_high,
        verdict_run_ids=run_ids,
        per_step_new=[0] * steps,
    )


def test_metrics_aggregate_seed_rates_and_method_only_signatures() -> None:
    logs = [
        _log(
            "random",
            0,
            steps=100,
            signatures=["shared", "random-only"],
            first_violation=10,
            first_high=None,
            run_ids=["r1"],
        ),
        _log(
            "random",
            1,
            steps=200,
            signatures=["shared", "random-second"],
            first_violation=20,
            first_high=50,
            run_ids=["r2"],
        ),
        _log(
            "ppo",
            0,
            steps=100,
            signatures=["shared", "ppo-only"],
            first_violation=5,
            first_high=25,
            run_ids=["p1"],
        ),
    ]
    verdicts = [
        {"run_id": "r1", "violations": [{"severity": "medium"}]},
        {"run_id": "r2", "violations": [{"severity": "high"}]},
        {"run_id": "p1", "violations": [{"severity": "high"}]},
        {"run_id": "unrelated", "violations": [{"severity": "low"}]},
    ]

    result = metrics(logs, verdicts=verdicts)

    random = result["by_app_method"]["shop"]["random"]
    assert random["n"] == 2
    assert random["unique_signatures_per_1000"] == {"mean": 15.0, "sd": 5.0}
    assert random["ttfv"] == {"mean": 15.0, "sd": 5.0}
    assert random["ttf_high"] == {"mean": 75.0, "sd": 25.0}
    assert random["severity_mix"] == {"low": 0, "medium": 1, "high": 1}
    assert result["signature_union"]["random"] == ["random-only", "random-second", "shared"]
    assert result["method_only"]["ppo"] == ["ppo-only"]


def test_train_ppo_logs_each_vector_environment_step() -> None:
    tools, contracts = load_app_records("shop")

    def env_fn() -> SpecXFuzzEnv:
        return SpecXFuzzEnv(
            FakeSandbox(),
            "shop",
            tools,
            contracts,
            source="s1",
            horizon=25,
            post_observe_ms=0,
            seed=7,
        )

    _, log = train_ppo([env_fn, env_fn], total_steps=8, seed=7)

    assert log.method == "ppo"
    assert log.steps == 8
    assert len(log.per_step_new) == 8
    assert len(log.verdict_run_ids) >= 8
    assert np.asarray(log.per_step_new).min() >= 0


def test_run_experiment_writes_three_methods_and_provenance(tmp_path: Path) -> None:
    from specx.safety.s1.run import run_experiment

    result = run_experiment(
        ["shop"],
        steps=8,
        seeds=1,
        out=tmp_path,
        client_factory=FakeSandbox,
        ppo_envs=2,
        post_observe_ms=0,
        max_seconds=60,
    )

    assert result["seeds_completed"] == 1
    assert set(result["by_app_method"]["shop"]) == {"random", "coverage", "ppo"}
    assert len(list((tmp_path / "logs").glob("*.json"))) == 3
    assert (tmp_path / "ckpt" / "shop-seed0.zip").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "run.json").exists()


@pytest.mark.sandbox
def test_ppo_real_sandbox_writes_s1_verdicts(tmp_path: Path) -> None:
    del tmp_path
    tools, contracts = load_app_records("shop")
    output = verdicts_path("s1")
    before = len(output.read_text().splitlines()) if output.exists() else 0

    def env_fn() -> SpecXFuzzEnv:
        from specx.client.sandbox import SandboxClient

        return SpecXFuzzEnv(
            SandboxClient(),
            "shop",
            tools,
            contracts,
            source="s1",
            horizon=25,
            post_observe_ms=300,
            seed=17,
        )

    train_ppo([env_fn] * 4, total_steps=30, seed=17)

    assert len(output.read_text().splitlines()) > before
