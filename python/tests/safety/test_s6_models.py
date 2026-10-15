import json
from pathlib import Path

import numpy as np
import pytest
import torch
from jsonschema import Draft202012Validator

from specx.safety.s6.models import LstmAE, load, save, sequences_for_model
from specx.safety.s6.score import score_run
from specx.safety.s6.synth import load_events, synthetic_runs
from specx.safety.s6.train import train

REPO_ROOT = Path(__file__).resolve().parents[3]
APPROVED_EVENTS = load_events(REPO_ROOT / "fixtures" / "events" / "approved_trace.jsonl")


@pytest.fixture(scope="module")
def trained_model_and_runs():
    approved = synthetic_runs(APPROVED_EVENTS, n=200, seed=7)
    model = train(approved, seed=7, epochs=6)
    return model, approved


def test_lstm_reconstruction_error_is_one_value_per_run() -> None:
    model = LstmAE()
    batch = torch.zeros((3, 8, 14), dtype=torch.float32)

    errors = model.reconstruction_error(batch)

    assert errors.shape == (3,)
    assert torch.all(errors >= 0)


def test_threshold_from_train_only(trained_model_and_runs) -> None:
    model, approved = trained_model_and_runs
    windows = np.concatenate([np.asarray(run.X, dtype=np.float64) for run in approved])
    scaled_windows = model.scaler.transform(windows)
    expected_if = float(np.percentile(-model.iforest.score_samples(scaled_windows), 99))
    sequences = sequences_for_model(model.scaler, approved, model.seq_len)
    expected_lstm = float(
        np.percentile(model.lstm.reconstruction_error(torch.from_numpy(sequences)).numpy(), 99)
    )

    assert model.thr_if == expected_if
    assert model.thr_lstm == expected_lstm


def test_delayed_post_detection_and_held_out_fpr(trained_model_and_runs) -> None:
    model, _ = trained_model_and_runs
    leaked = synthetic_runs(APPROVED_EVENTS, n=50, seed=17, leak_kind="delayed_post")
    benign = synthetic_runs(APPROVED_EVENTS, n=50, seed=23)

    detection_rate = np.mean([score_run(model, run)["flagged"] for run in leaked])
    false_positive_rate = np.mean([score_run(model, run)["flagged"] for run in benign])

    assert detection_rate >= 0.8
    assert false_positive_rate <= 0.1


def test_score_output_validates_as_verdict_anomaly(trained_model_and_runs) -> None:
    model, approved = trained_model_and_runs
    anomaly = score_run(model, approved[0])
    schema = json.loads((REPO_ROOT / "contracts" / "verdict.schema.json").read_text())

    Draft202012Validator(schema["properties"]["anomaly"]).validate(anomaly)


def test_save_load_round_trip_preserves_scores(trained_model_and_runs, tmp_path: Path) -> None:
    model, approved = trained_model_and_runs
    model_path = tmp_path / "model"
    before = score_run(model, approved[0])

    save(model, model_path)
    restored = load(model_path)

    assert score_run(restored, approved[0]) == before
