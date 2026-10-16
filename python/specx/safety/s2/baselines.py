"""Rule-based link and raw-feature MLP path baselines for S2."""

from typing import Any

import numpy as np
import torch

from specx.client.seeding import seed_everything
from specx.safety.s2.dataset import GraphData, PathExample
from specx.safety.s2.models import PathHead
from specx.safety.s2.train import classification_metrics, path_features, path_tensors


def _leaf_fields(schema: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for name, value in schema.get("properties", {}).items():
        if not isinstance(value, dict):
            continue
        nested = value.get("items") if value.get("type") == "array" else value
        if isinstance(nested, dict) and nested.get("properties"):
            fields.update(_leaf_fields(nested))
        else:
            fields.add(str(name))
    return fields


def rule_link(tools: list[dict[str, Any]]) -> set[tuple[str, str]]:
    predicted: set[tuple[str, str]] = set()
    for source in tools:
        output_fields = _leaf_fields(source.get("output_schema", {}))
        for target in tools:
            if target["tool_id"] == source["tool_id"]:
                continue
            inputs = set(target.get("input_schema", {}).get("properties", {}))
            if output_fields & inputs:
                predicted.add((str(source["tool_id"]), str(target["tool_id"])))
    return predicted


def mlp_path(
    graph: GraphData,
    train_examples: list[PathExample],
    test_examples: list[PathExample],
    *,
    seed: int = 0,
    epochs: int = 200,
) -> tuple[PathHead, dict[str, float]]:
    if epochs <= 0 or not train_examples or not test_examples:
        raise ValueError("path training requires non-empty splits and positive epochs")
    seed_everything(seed)
    embeddings = torch.as_tensor(graph.x, dtype=torch.float32)
    train_data = path_tensors(train_examples)
    test_data = path_tensors(test_examples)
    head = PathHead(embeddings.shape[1])
    optimizer = torch.optim.Adam(head.parameters(), lr=1e-2)
    loss_fn = torch.nn.BCELoss()
    for _ in range(epochs):
        head.train()
        optimizer.zero_grad()
        probabilities = head(path_features(embeddings, train_data))
        loss_fn(probabilities, train_data.labels).backward()
        optimizer.step()
    head.eval()
    with torch.no_grad():
        probabilities = head(path_features(embeddings, test_data)).numpy()
    labels = test_data.labels.numpy().astype(np.int64)
    return head, classification_metrics(labels, probabilities)
