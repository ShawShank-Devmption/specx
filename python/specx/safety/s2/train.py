"""Train S2 GCN link-prediction and path-risk models."""

from dataclasses import dataclass
from typing import cast

import numpy as np
import torch
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from specx.client.seeding import seed_everything
from specx.safety.s2.dataset import GraphData, PathExample
from specx.safety.s2.models import GCNEncoder, LinkHead, PathHead


@dataclass(frozen=True)
class PathTensors:
    prefix_nodes: torch.Tensor
    prefix_owners: torch.Tensor
    prefix_counts: torch.Tensor
    targets: torch.Tensor
    auxiliary: torch.Tensor
    labels: torch.Tensor


def classification_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    predicted = (probabilities >= 0.5).astype(np.int64)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predicted, average="binary", zero_division=0
    )
    auc = roc_auc_score(labels, probabilities) if len(np.unique(labels)) > 1 else 0.5
    return {
        "auc": float(auc),
        "p": float(precision),
        "r": float(recall),
        "f1": float(f1),
    }


def graph_tensors(graph: GraphData) -> tuple[torch.Tensor, torch.Tensor]:
    return (
        torch.as_tensor(graph.x, dtype=torch.float32),
        torch.as_tensor(graph.edge_index, dtype=torch.long),
    )


def train_link(
    graph: GraphData,
    pairs: np.ndarray,
    labels: np.ndarray,
    *,
    test_pairs: np.ndarray | None = None,
    test_labels: np.ndarray | None = None,
    seed: int = 0,
    epochs: int = 200,
) -> tuple[GCNEncoder, LinkHead, dict[str, float]]:
    if epochs <= 0 or len(pairs) == 0 or len(pairs) != len(labels):
        raise ValueError("link training requires matching non-empty examples and positive epochs")
    seed_everything(seed)
    x, edge_index = graph_tensors(graph)
    train_pairs = torch.as_tensor(pairs, dtype=torch.long)
    train_labels = torch.as_tensor(labels, dtype=torch.float32)
    encoder, head = GCNEncoder(), LinkHead()
    optimizer = torch.optim.Adam([*encoder.parameters(), *head.parameters()], lr=1e-2)
    loss_fn = torch.nn.BCELoss()
    for _ in range(epochs):
        encoder.train()
        optimizer.zero_grad()
        probabilities = head(encoder(x, edge_index), train_pairs)
        loss_fn(probabilities, train_labels).backward()
        optimizer.step()

    eval_pairs = pairs if test_pairs is None else test_pairs
    eval_labels = labels if test_labels is None else test_labels
    encoder.eval()
    with torch.no_grad():
        probabilities = head(
            encoder(x, edge_index), torch.as_tensor(eval_pairs, dtype=torch.long)
        ).numpy()
    return encoder, head, classification_metrics(np.asarray(eval_labels), probabilities)


def path_tensors(examples: list[PathExample]) -> PathTensors:
    prefix_nodes: list[int] = []
    prefix_owners: list[int] = []
    counts: list[float] = []
    for owner, example in enumerate(examples):
        prefix_nodes.extend(example.prefix)
        prefix_owners.extend([owner] * len(example.prefix))
        counts.append(float(len(example.prefix)))
    return PathTensors(
        prefix_nodes=torch.as_tensor(prefix_nodes, dtype=torch.long),
        prefix_owners=torch.as_tensor(prefix_owners, dtype=torch.long),
        prefix_counts=torch.as_tensor(counts, dtype=torch.float32),
        targets=torch.as_tensor([example.target for example in examples], dtype=torch.long),
        auxiliary=torch.as_tensor(
            [[float(len(example.prefix)), example.mutation] for example in examples],
            dtype=torch.float32,
        ),
        labels=torch.as_tensor([example.label for example in examples], dtype=torch.float32),
    )


def path_features(embeddings: torch.Tensor, tensors: PathTensors) -> torch.Tensor:
    prefix = torch.zeros((len(tensors.targets), embeddings.shape[1]), dtype=embeddings.dtype)
    if len(tensors.prefix_nodes):
        prefix.index_add_(0, tensors.prefix_owners, embeddings[tensors.prefix_nodes])
    divisor = tensors.prefix_counts.clamp(min=1).unsqueeze(1)
    prefix = prefix / divisor
    return torch.cat((prefix, embeddings[tensors.targets], tensors.auxiliary), dim=1)


def train_path(
    graph: GraphData,
    train_examples: list[PathExample],
    test_examples: list[PathExample],
    *,
    seed: int = 0,
    epochs: int = 200,
) -> tuple[GCNEncoder, PathHead, dict[str, float]]:
    if epochs <= 0 or not train_examples or not test_examples:
        raise ValueError("path training requires non-empty splits and positive epochs")
    seed_everything(seed)
    x, edge_index = graph_tensors(graph)
    train_data = path_tensors(train_examples)
    test_data = path_tensors(test_examples)
    encoder, head = GCNEncoder(), PathHead(64)
    optimizer = torch.optim.Adam([*encoder.parameters(), *head.parameters()], lr=1e-2)
    loss_fn = torch.nn.BCELoss()
    for _ in range(epochs):
        encoder.train()
        optimizer.zero_grad()
        embeddings = encoder(x, edge_index)
        probabilities = head(path_features(embeddings, train_data))
        loss_fn(probabilities, train_data.labels).backward()
        optimizer.step()

    encoder.eval()
    with torch.no_grad():
        probabilities = head(path_features(encoder(x, edge_index), test_data)).numpy()
    labels = test_data.labels.numpy().astype(np.int64)
    return encoder, head, classification_metrics(labels, probabilities)


def predict_links(
    graph: GraphData, encoder: GCNEncoder, head: LinkHead, pairs: np.ndarray
) -> np.ndarray:
    x, edge_index = graph_tensors(graph)
    encoder.eval()
    with torch.no_grad():
        return cast(
            np.ndarray,
            head(encoder(x, edge_index), torch.as_tensor(pairs, dtype=torch.long)).numpy(),
        )
