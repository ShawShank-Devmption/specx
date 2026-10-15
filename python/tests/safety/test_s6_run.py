import json
from pathlib import Path

import pytest

from specx.client.fake import FakeSandbox
from specx.client.sandbox import SandboxClient
from specx.safety.s6.collect import TraceRun
from specx.safety.s6.inject import evaluate_leaks
from specx.safety.s6.run import run_experiment


def test_s6_run_writes_metrics_model_and_provenance(tmp_path: Path) -> None:
    metrics = run_experiment(
        ["shop"],
        out=tmp_path,
        seed=13,
        client_factory=FakeSandbox,
        runs_per_tool=2,
        min_train_runs=10,
        leaks_per_kind=2,
        benign_runs=2,
        epochs=1,
        max_workers=2,
    )

    assert metrics["n_train"] >= 10
    assert metrics["n_attempted"] >= 10
    assert metrics["n_excluded"] >= 1
    assert set(metrics["per_kind"]) == {
        "delayed_post",
        "storage_write",
        "third_party_fetch",
        "background_poll",
    }
    assert metrics["benign"]["n"] == 2
    assert all(result["n"] == 2 for result in metrics["per_kind"].values())
    assert set(metrics["thresholds"]) == {"iforest", "lstm"}
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "run.json").exists()
    assert (tmp_path / "model" / "metadata.json").exists()
    run_record = json.loads((tmp_path / "run.json").read_text())
    assert run_record["args"]["seed"] == 13
    assert run_record["args"]["min_train_runs"] == 10
    assert run_record["duration_seconds"] >= 0


def test_evaluation_counts_are_totals_across_apps(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_evaluate_batch(**kwargs: object) -> list[TraceRun]:
        count = int(kwargs["count"])
        app = str(kwargs["app"])
        return [TraceRun(app=app, verdict={}, events=[]) for _ in range(count)]

    monkeypatch.setattr("specx.safety.s6.inject._evaluate_batch", fake_evaluate_batch)

    evaluation = evaluate_leaks(
        ["shop", "admin"],
        leaks_per_kind=5,
        benign_runs=7,
        max_workers=2,
    )

    assert all(len(runs) == 5 for runs in evaluation.injected.values())
    assert len(evaluation.benign) == 7


@pytest.mark.sandbox
def test_s6_run_real_sandbox_smoke(tmp_path: Path) -> None:
    assert SandboxClient().health()["ok"] is True

    metrics = run_experiment(
        ["shop"],
        out=tmp_path,
        seed=3,
        client_factory=SandboxClient,
        runs_per_tool=1,
        min_train_runs=0,
        leaks_per_kind=1,
        benign_runs=1,
        epochs=1,
        max_workers=2,
    )

    assert metrics["n_train"] >= 1
    assert metrics["benign"]["n"] == 1
