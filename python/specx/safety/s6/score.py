"""Score S6 runs and attach anomaly results to verdict JSONL records."""

import json
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import torch
import typer
from jsonschema import Draft202012Validator

from specx.client.paths import repo_root
from specx.safety.s6.features import RunWindows, windows_from_jsonl
from specx.safety.s6.models import S6Model, load, sequences_for_model


def score_run(model: S6Model, run: RunWindows) -> dict[str, Any]:
    windows = np.asarray(run.X, dtype=np.float64)
    scaled_windows = model.scaler.transform(windows)
    window_scores = -model.iforest.score_samples(scaled_windows)
    iforest_score = float(np.max(window_scores))
    sequence = sequences_for_model(model.scaler, [run], model.seq_len)
    lstm_error = float(model.lstm.reconstruction_error(torch.from_numpy(sequence)).numpy()[0])
    flagged_windows = np.flatnonzero(window_scores > model.thr_if).astype(int).tolist()
    return {
        "iforest_score": iforest_score,
        "lstm_error": lstm_error,
        "flagged": bool(iforest_score > model.thr_if or lstm_error > model.thr_lstm),
        "flagged_windows": flagged_windows,
    }


def _schema_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "verdict.schema.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("contracts/verdict.schema.json not found")


def score_verdicts(input_path: Path, output_path: Path, model_path: Path) -> None:
    model = load(model_path)
    schema = json.loads(_schema_path().read_text())
    validator = Draft202012Validator(schema)
    verdicts = [json.loads(line) for line in input_path.read_text().splitlines() if line.strip()]
    for verdict in verdicts:
        artifacts = verdict.get("artifacts", {})
        events_path = artifacts.get("events_path")
        if not events_path:
            raise ValueError(f"verdict {verdict.get('run_id')} has no artifacts.events_path")
        events_file = Path(events_path)
        if not events_file.is_absolute():
            events_file = repo_root() / events_file
        runs = windows_from_jsonl(events_file)
        matching = [run for run in runs if run.run_id == verdict.get("run_id")]
        if len(matching) != 1:
            raise ValueError(f"expected one event run for verdict {verdict.get('run_id')}")
        verdict["anomaly"] = score_run(model, matching[0])
        validator.validate(verdict)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in verdicts))
    temporary.replace(output_path)


def main(
    input_path: Annotated[Path, typer.Option("--in", exists=True, dir_okay=False)],
    output_path: Annotated[Path | None, typer.Option("--out", dir_okay=False)] = None,
    model_path: Annotated[Path, typer.Option("--model", file_okay=False)] = Path(
        "results/s6/model"
    ),
) -> None:
    score_verdicts(input_path, output_path or input_path, model_path)


if __name__ == "__main__":
    typer.run(main)
