"""Neural and scikit-learn model containers for the S6 anomaly layer."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import joblib
import numpy as np
import torch
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from torch import Tensor, nn

from specx.safety.s6.features import FEATURES, RunWindows


class LstmAE(nn.Module):
    """Sequence autoencoder used to detect run-level temporal anomalies."""

    def __init__(self, n_features: int = 14, hidden: int = 32, latent: int = 16):
        super().__init__()
        self.n_features = n_features
        self.hidden = hidden
        self.latent = latent
        self.encoder = nn.LSTM(n_features, hidden, num_layers=1, batch_first=True)
        self.to_latent = nn.Linear(hidden, latent)
        self.from_latent = nn.Linear(latent, hidden)
        self.decoder = nn.LSTM(hidden, hidden, num_layers=1, batch_first=True)
        self.output = nn.Linear(hidden, n_features)

    def forward(self, x: Tensor) -> Tensor:
        _, (hidden_state, _) = self.encoder(x)
        latent = self.to_latent(hidden_state[-1])
        decoded_seed = self.from_latent(latent).unsqueeze(1).expand(-1, x.shape[1], -1)
        decoded, _ = self.decoder(decoded_seed)
        return cast(Tensor, self.output(decoded))

    def reconstruction_error(self, x: Tensor) -> Tensor:
        self.eval()
        with torch.no_grad():
            return torch.mean((self(x) - x) ** 2, dim=(1, 2))


@dataclass
class S6Model:
    iforest: IsolationForest
    lstm: LstmAE
    scaler: StandardScaler
    thr_if: float
    thr_lstm: float
    seq_len: int


def sequences_for_model(scaler: StandardScaler, runs: list[RunWindows], seq_len: int) -> np.ndarray:
    """Scale real windows while leaving sequence padding at neutral zero."""
    sequences = np.zeros((len(runs), seq_len, len(FEATURES)), dtype=np.float32)
    for run_index, run in enumerate(runs):
        windows = np.asarray(run.X, dtype=np.float64)
        if windows.ndim != 2 or windows.shape[1] != len(FEATURES):
            raise ValueError(f"run {run.run_id} must have {len(FEATURES)} features per window")
        scaled = scaler.transform(windows).astype(np.float32)
        copied = min(seq_len, scaled.shape[0])
        sequences[run_index, :copied] = scaled[:copied]
    return sequences


def save(model: S6Model, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(model.iforest, path / "iforest.joblib")
    joblib.dump(model.scaler, path / "scaler.joblib")
    torch.save(model.lstm.state_dict(), path / "lstm.pt")
    metadata = {
        "thr_if": model.thr_if,
        "thr_lstm": model.thr_lstm,
        "seq_len": model.seq_len,
        "n_features": model.lstm.n_features,
        "hidden": model.lstm.hidden,
        "latent": model.lstm.latent,
    }
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def load(path: Path) -> S6Model:
    metadata = json.loads((path / "metadata.json").read_text())
    lstm = LstmAE(
        n_features=int(metadata["n_features"]),
        hidden=int(metadata["hidden"]),
        latent=int(metadata["latent"]),
    )
    state = torch.load(path / "lstm.pt", map_location="cpu", weights_only=True)
    lstm.load_state_dict(state)
    lstm.eval()
    return S6Model(
        iforest=joblib.load(path / "iforest.joblib"),
        lstm=lstm,
        scaler=joblib.load(path / "scaler.joblib"),
        thr_if=float(metadata["thr_if"]),
        thr_lstm=float(metadata["thr_lstm"]),
        seq_len=int(metadata["seq_len"]),
    )
