"""End-to-end S6 collection, training, leak evaluation, and metrics CLI."""

import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from specx.client.io import write_json, write_jsonl
from specx.client.paths import repo_root, verdicts_path
from specx.client.sandbox import SandboxClient
from specx.client.seeding import seed_everything
from specx.safety.s6.collect import TraceRun, collect_approved
from specx.safety.s6.features import RunWindows, windows_for_run
from specx.safety.s6.inject import LEAK_KINDS, evaluate_leaks
from specx.safety.s6.models import save
from specx.safety.s6.score import score_run, score_verdicts
from specx.safety.s6.train import train


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _windows(runs: list[TraceRun]) -> list[RunWindows]:
    return [windows_for_run(run.events) for run in runs]


def _rates(model: Any, runs: list[TraceRun]) -> dict[str, float | int]:
    scores = [score_run(model, window) for window in _windows(runs)]
    count = len(scores)
    if count == 0:
        return {"n": 0, "det_if": 0.0, "det_lstm": 0.0, "det_both": 0.0}
    return {
        "n": count,
        "det_if": sum(score["iforest_score"] > model.thr_if for score in scores) / count,
        "det_lstm": sum(score["lstm_error"] > model.thr_lstm for score in scores) / count,
        "det_both": sum(score["flagged"] for score in scores) / count,
    }


def _resolve_out(path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root() / path


def run_experiment(
    apps: list[str],
    *,
    out: Path,
    seed: int,
    client_factory: Callable[[], SandboxClient] = SandboxClient,
    runs_per_tool: int = 20,
    min_train_runs: int = 300,
    leaks_per_kind: int = 25,
    benign_runs: int = 100,
    epochs: int = 30,
    max_workers: int = 4,
    post_observe_ms: int = 2000,
    score_f1: bool = False,
) -> dict[str, Any]:
    if not apps:
        raise ValueError("at least one app is required")
    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    seed_everything(seed)
    output = _resolve_out(out)
    output.mkdir(parents=True, exist_ok=True)

    collection = collect_approved(
        apps,
        runs_per_tool=runs_per_tool,
        min_runs=min_train_runs,
        seed=seed,
        client_factory=client_factory,
        max_workers=max_workers,
        post_observe_ms=post_observe_ms,
    )
    approved = _windows(collection.runs)
    if not approved:
        raise RuntimeError("S6 collection produced no approved training runs")
    model = train(approved, seed=seed, epochs=epochs)
    save(model, output / "model")

    evaluation = evaluate_leaks(
        apps,
        leaks_per_kind=leaks_per_kind,
        benign_runs=benign_runs,
        seed=seed + 1_000_000,
        client_factory=client_factory,
        max_workers=max_workers,
        post_observe_ms=post_observe_ms,
    )
    per_kind = {kind: _rates(model, evaluation.injected[kind]) for kind in LEAK_KINDS}
    benign_rates = _rates(model, evaluation.benign)
    benign = {
        "n": benign_rates["n"],
        "fpr_if": benign_rates["det_if"],
        "fpr_lstm": benign_rates["det_lstm"],
        "fpr_both": benign_rates["det_both"],
    }
    contract_only = {
        kind: (
            sum(bool(run.verdict["violations"]) for run in evaluation.injected[kind])
            / len(evaluation.injected[kind])
            if evaluation.injected[kind]
            else 0.0
        )
        for kind in LEAK_KINDS
    }
    metrics: dict[str, Any] = {
        "n_train": len(collection.runs),
        "n_attempted": collection.n_attempted,
        "n_excluded": collection.n_excluded,
        "thresholds": {"iforest": model.thr_if, "lstm": model.thr_lstm},
        "seq_len": model.seq_len,
        "split": {
            "unit": "run_id",
            "train": "approved collection sessions",
            "test": "fresh injected and benign sessions",
        },
        "per_kind": per_kind,
        "benign": benign,
        "contract_only_detection": contract_only,
    }
    write_json(output / "metrics.json", metrics)
    write_jsonl(
        output / "approved.events.jsonl", (event for run in collection.runs for event in run.events)
    )
    write_jsonl(output / "approved.verdicts.jsonl", (run.verdict for run in collection.runs))
    injected_runs = [run for kind in LEAK_KINDS for run in evaluation.injected[kind]]
    write_jsonl(
        output / "injected.events.jsonl", (event for run in injected_runs for event in run.events)
    )
    write_jsonl(output / "injected.verdicts.jsonl", (run.verdict for run in injected_runs))
    write_jsonl(
        output / "benign.events.jsonl", (event for run in evaluation.benign for event in run.events)
    )
    write_jsonl(output / "benign.verdicts.jsonl", (run.verdict for run in evaluation.benign))

    if score_f1:
        f1_path = verdicts_path("f1")
        if not f1_path.exists():
            raise FileNotFoundError("results/verdicts/f1.jsonl is required for S6 scoring")
        score_verdicts(f1_path, f1_path, output / "model")

    finished_at = datetime.now(UTC)
    run_record = {
        "git_sha": _git_sha(),
        "args": {
            "apps": apps,
            "out": str(output),
            "seed": seed,
            "runs_per_tool": runs_per_tool,
            "min_train_runs": min_train_runs,
            "leaks_per_kind": leaks_per_kind,
            "benign_runs": benign_runs,
            "epochs": epochs,
            "max_workers": max_workers,
            "post_observe_ms": post_observe_ms,
        },
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": time.perf_counter() - started_clock,
    }
    write_json(output / "run.json", run_record)
    return metrics


def main(
    apps: Annotated[str, typer.Option("--apps")] = "shop,admin",
    out: Annotated[Path, typer.Option("--out")] = Path("results/s6"),
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    run_experiment(
        [app.strip() for app in apps.split(",") if app.strip()],
        out=out,
        seed=seed,
        score_f1=True,
    )


if __name__ == "__main__":
    typer.run(main)
