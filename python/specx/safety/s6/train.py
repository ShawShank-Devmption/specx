"""Train the S6 Isolation Forest and LSTM autoencoder on approved runs."""

import random

import numpy as np
import torch
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from specx.safety.s6.features import RunWindows
from specx.safety.s6.models import LstmAE, S6Model, sequences_for_model


def train(approved: list[RunWindows], *, seed: int, epochs: int = 30, seq_len: int = 8) -> S6Model:
    if not approved:
        raise ValueError("at least one approved run is required")
    if epochs < 0:
        raise ValueError("epochs must be non-negative")

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)

    windows = np.concatenate([np.asarray(run.X, dtype=np.float64) for run in approved])
    scaler = StandardScaler().fit(windows)
    scaled_windows = scaler.transform(windows)
    iforest = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=seed,
        n_jobs=1,
    ).fit(scaled_windows)

    sequences = sequences_for_model(scaler, approved, seq_len)
    tensors = torch.from_numpy(sequences)
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        TensorDataset(tensors),
        batch_size=min(32, len(approved)),
        shuffle=True,
        generator=generator,
    )
    lstm = LstmAE(n_features=sequences.shape[2])
    optimiser = torch.optim.Adam(lstm.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    lstm.train()
    for _ in range(epochs):
        for (batch,) in loader:
            optimiser.zero_grad()
            loss = loss_fn(lstm(batch), batch)
            loss.backward()
            optimiser.step()
    lstm.eval()

    if_scores = -iforest.score_samples(scaled_windows)
    lstm_scores = lstm.reconstruction_error(tensors).numpy()
    return S6Model(
        iforest=iforest,
        lstm=lstm,
        scaler=scaler,
        thr_if=float(np.percentile(if_scores, 99)),
        thr_lstm=float(np.percentile(lstm_scores, 99)),
        seq_len=seq_len,
    )
