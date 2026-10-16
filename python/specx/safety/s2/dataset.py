"""Build S2 graph tensors and session-disjoint path-risk examples."""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from specx.client.io import read_json
from specx.client.schemas import validate

RISK_LEVELS = ("read", "write", "delete", "payment")
EDGE_TYPES = ("order", "state", "data")
NODE_FEATS = 9


class GraphData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app: str
    node_ids: list[str]
    x: np.ndarray
    edge_index: np.ndarray
    edge_type: np.ndarray


class PathExample(BaseModel):
    prefix: list[int]
    target: int
    mutation: float
    label: float
    session_id: str


def load_graph(path: Path) -> GraphData:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a workflow graph object")
    validate("workflow_graph", raw)
    node_ids = [str(node["id"]) for node in raw["nodes"]]
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    incoming = Counter(str(edge["dst"]) for edge in raw["edges"])
    outgoing = Counter(str(edge["src"]) for edge in raw["edges"])
    rows: list[list[float]] = []
    for node in raw["nodes"]:
        risk = [float(node["risk_level"] == level) for level in RISK_LEVELS]
        rows.append(
            [
                *risk,
                float(incoming[node["id"]]),
                float(outgoing[node["id"]]),
                float(len(node["state_writes"])),
                float(node.get("status") == "quarantined"),
                float(node.get("violation_rate", 0.0)),
            ]
        )
    confirmed = [
        edge
        for edge in raw["edges"]
        if edge["evidence"] in {"trace", "contract"} and edge.get("label") is True
    ]
    edge_index = np.asarray(
        [[node_index[edge["src"]], node_index[edge["dst"]]] for edge in confirmed],
        dtype=np.int64,
    )
    edge_index = edge_index.T if edge_index.size else np.empty((2, 0), dtype=np.int64)
    edge_type = np.asarray([EDGE_TYPES.index(edge["type"]) for edge in confirmed], dtype=np.int64)
    return GraphData(
        app=str(raw["app"]),
        node_ids=node_ids,
        x=np.asarray(rows, dtype=np.float64),
        edge_index=edge_index,
        edge_type=edge_type,
    )


def link_examples(graph: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    validate("workflow_graph", graph)
    node_ids = [str(node["id"]) for node in graph["nodes"]]
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    positives = sorted(
        {
            (node_index[edge["src"]], node_index[edge["dst"]])
            for edge in graph["edges"]
            if edge["type"] == "data" and edge.get("label") is True
        }
    )
    existing = {(str(edge["src"]), str(edge["dst"])) for edge in graph["edges"]}
    candidates = [
        (src_index, dst_index)
        for src_index, src in enumerate(node_ids)
        for dst_index, dst in enumerate(node_ids)
        if src != dst and (src, dst) not in existing
    ]
    if len(candidates) < len(positives):
        raise ValueError("not enough absent edges to balance link examples")
    negatives = candidates[: len(positives)]
    pairs = np.asarray([*positives, *negatives], dtype=np.int64)
    labels = np.asarray([1] * len(positives) + [0] * len(negatives), dtype=np.int64)
    return pairs, labels


def _canonical_args(verdicts: list[dict[str, Any]]) -> dict[str, str]:
    preferred: dict[str, list[str]] = defaultdict(list)
    fallback: dict[str, list[str]] = defaultdict(list)
    for verdict in verdicts:
        tool_id = verdict.get("tool_id")
        args = verdict.get("args")
        if not isinstance(tool_id, str) or not isinstance(args, dict):
            continue
        encoded = json.dumps(args, sort_keys=True, separators=(",", ":"))
        fallback[tool_id].append(encoded)
        if verdict.get("source") in {"f1", "s6_approved", "fixture"}:
            preferred[tool_id].append(encoded)
    canonical: dict[str, str] = {}
    for tool_id, values in fallback.items():
        choices = preferred.get(tool_id) or values
        canonical[tool_id] = Counter(choices).most_common(1)[0][0]
    return canonical


def path_examples(graph: GraphData, verdicts: list[dict[str, Any]]) -> list[PathExample]:
    node_index = {node_id: index for index, node_id in enumerate(graph.node_ids)}
    canonical = _canonical_args(verdicts)
    examples: list[PathExample] = []
    for verdict in verdicts:
        tool_id = verdict.get("tool_id")
        session_id = verdict.get("session_id")
        if tool_id not in node_index or not isinstance(session_id, str):
            continue
        prefix_ids = verdict.get("sequence_prefix", [])
        prefix = [node_index[item] for item in prefix_ids if item in node_index]
        encoded = json.dumps(verdict.get("args", {}), sort_keys=True, separators=(",", ":"))
        examples.append(
            PathExample(
                prefix=prefix,
                target=node_index[tool_id],
                mutation=float(encoded != canonical.get(tool_id, encoded)),
                label=float(bool(verdict.get("violations"))),
                session_id=session_id,
            )
        )
    return examples


def split_by_session(
    examples: list[PathExample], frac: float = 0.3, seed: int = 0
) -> tuple[list[PathExample], list[PathExample]]:
    if not 0.0 < frac < 1.0:
        raise ValueError("frac must be between zero and one")
    sessions = sorted({example.session_id for example in examples})
    if len(sessions) < 2:
        raise ValueError("session-disjoint split requires at least two sessions")
    rng = np.random.default_rng(seed)
    rng.shuffle(sessions)
    n_test = min(len(sessions) - 1, max(1, math.ceil(len(sessions) * frac)))
    test_sessions = set(sessions[:n_test])
    train = [example for example in examples if example.session_id not in test_sessions]
    test = [example for example in examples if example.session_id in test_sessions]
    return train, test
