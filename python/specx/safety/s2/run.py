"""Run the S2 link-prediction and path-risk experiment."""

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import typer

from specx.client.io import read_json, read_jsonl, write_json
from specx.client.paths import repo_root
from specx.client.schemas import validate
from specx.safety.s2.baselines import mlp_path, rule_link
from specx.safety.s2.dataset import (
    GraphData,
    PathExample,
    load_graph,
    path_examples,
    split_by_session,
)
from specx.safety.s2.train import (
    classification_metrics,
    predict_links,
    train_link,
    train_path,
)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def combine_graphs(graphs: list[GraphData]) -> tuple[GraphData, dict[str, int]]:
    if not graphs:
        raise ValueError("at least one graph is required")
    offsets: dict[str, int] = {}
    node_ids: list[str] = []
    xs: list[np.ndarray] = []
    edges: list[np.ndarray] = []
    edge_types: list[np.ndarray] = []
    for graph in graphs:
        if graph.app in offsets:
            raise ValueError(f"duplicate app graph: {graph.app}")
        offset = len(node_ids)
        offsets[graph.app] = offset
        node_ids.extend(graph.node_ids)
        xs.append(graph.x)
        if graph.edge_index.shape[1]:
            edges.append(graph.edge_index + offset)
            edge_types.append(graph.edge_type)
    return (
        GraphData(
            app="+".join(graph.app for graph in graphs),
            node_ids=node_ids,
            x=np.concatenate(xs),
            edge_index=(
                np.concatenate(edges, axis=1) if edges else np.empty((2, 0), dtype=np.int64)
            ),
            edge_type=(np.concatenate(edge_types) if edge_types else np.empty(0, dtype=np.int64)),
        ),
        offsets,
    )


def split_link_examples(
    pairs: np.ndarray,
    labels: np.ndarray,
    *,
    frac: float = 0.3,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Make a deterministic class-stratified split without pair leakage."""
    if len(pairs) != len(labels) or len(pairs) < 4:
        raise ValueError("link split requires at least four matching examples")
    if not 0.0 < frac < 1.0:
        raise ValueError("frac must be between zero and one")
    rng = np.random.default_rng(seed)
    train_indices: list[int] = []
    test_indices: list[int] = []
    for label in sorted(np.unique(labels)):
        indices = np.flatnonzero(labels == label)
        if len(indices) < 2:
            raise ValueError("each link class needs at least two examples")
        rng.shuffle(indices)
        n_test = min(len(indices) - 1, max(1, int(np.ceil(len(indices) * frac))))
        test_indices.extend(indices[:n_test].tolist())
        train_indices.extend(indices[n_test:].tolist())
    rng.shuffle(train_indices)
    rng.shuffle(test_indices)
    return (
        pairs[train_indices],
        labels[train_indices],
        pairs[test_indices],
        labels[test_indices],
    )


def combined_link_examples(
    graphs: list[dict[str, Any]], offsets: dict[str, int], *, seed: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Balance confirmed data links with absent pairs from the disjoint union."""
    positives: set[tuple[int, int]] = set()
    existing: set[tuple[int, int]] = set()
    n_nodes = sum(len(graph["nodes"]) for graph in graphs)
    for graph in graphs:
        offset = offsets[str(graph["app"])]
        index = {str(node["id"]): local + offset for local, node in enumerate(graph["nodes"])}
        for edge in graph["edges"]:
            pair = (index[str(edge["src"])], index[str(edge["dst"])])
            existing.add(pair)
            if edge["type"] == "data" and edge.get("label") is True:
                positives.add(pair)
    candidates = [
        (source, target)
        for source in range(n_nodes)
        for target in range(n_nodes)
        if source != target and (source, target) not in existing
    ]
    if len(candidates) < len(positives):
        raise ValueError("not enough absent disjoint-union edges to balance link examples")
    rng = np.random.default_rng(seed)
    rng.shuffle(candidates)
    positive_list = sorted(positives)
    pairs = np.asarray([*positive_list, *candidates[: len(positive_list)]], dtype=np.int64)
    labels = np.asarray([1] * len(positive_list) + [0] * len(positive_list), dtype=np.int64)
    return pairs, labels


def append_gnn_edges(graph: dict[str, Any], predictions: list[dict[str, Any]]) -> int:
    """Append previously absent predictions and validate the resulting graph."""
    existing = {
        (edge["src"], edge["dst"], edge["type"], edge.get("field")) for edge in graph["edges"]
    }
    added = 0
    for edge in predictions:
        key = (edge["src"], edge["dst"], edge["type"], edge.get("field"))
        if key not in existing:
            graph["edges"].append(edge)
            existing.add(key)
            added += 1
    validate("workflow_graph", graph)
    return added


def _mean_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    return {key: float(np.mean([row[key] for row in rows])) for key in ("auc", "p", "r", "f1")}


def _all_absent_pairs(raw: dict[str, Any], offset: int) -> tuple[np.ndarray, list[tuple[str, str]]]:
    node_ids = [str(node["id"]) for node in raw["nodes"]]
    existing = {(str(edge["src"]), str(edge["dst"])) for edge in raw["edges"]}
    ids = [
        (src, dst)
        for src in node_ids
        for dst in node_ids
        if src != dst and (src, dst) not in existing
    ]
    index = {node_id: number + offset for number, node_id in enumerate(node_ids)}
    pairs = np.asarray([(index[src], index[dst]) for src, dst in ids], dtype=np.int64).reshape(
        -1, 2
    )
    return pairs, ids


def _offset_path_examples(
    graph: GraphData, verdicts: list[dict[str, Any]], offset: int
) -> list[PathExample]:
    return [
        PathExample(
            prefix=[node + offset for node in example.prefix],
            target=example.target + offset,
            mutation=example.mutation,
            label=example.label,
            session_id=f"{graph.app}:{example.session_id}",
        )
        for example in path_examples(graph, verdicts)
    ]


def _load_tools(tools_dir: Path, app: str) -> list[dict[str, Any]]:
    path = tools_dir / f"{app}.tools.json"
    if not path.exists():
        fallback = repo_root() / "fixtures" / "tools" / f"{app}.tools.json"
        path = fallback if fallback.exists() else path
    tools = read_json(path)
    if not isinstance(tools, list):
        raise ValueError(f"{path} must contain a tool list")
    return tools


def run_experiment(
    *,
    graphs: Path,
    verdicts: Path,
    out: Path,
    tools: Path = Path("results/tools"),
    seed: int = 0,
    seeds: int = 3,
    epochs: int = 200,
) -> dict[str, Any]:
    if seeds <= 0 or epochs <= 0:
        raise ValueError("seeds and epochs must be positive")
    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    graph_dir, verdict_dir = _resolve(graphs), _resolve(verdicts)
    output, tools_dir = _resolve(out), _resolve(tools)
    graph_paths = sorted(graph_dir.glob("*.graph.json"))
    if not graph_paths:
        raise ValueError(f"no workflow graphs found in {graph_dir}")

    raw_graphs = [read_json(path) for path in graph_paths]
    loaded_graphs = [load_graph(path) for path in graph_paths]
    combined, offsets = combine_graphs(loaded_graphs)
    all_verdicts = [row for path in sorted(verdict_dir.glob("*.jsonl")) for row in read_jsonl(path)]
    if not all_verdicts:
        raise ValueError(f"no verdicts found in {verdict_dir}")

    all_paths: list[PathExample] = []
    rule_predictions: set[tuple[str, str]] = set()
    positive_fields: dict[tuple[str, str], str | None] = {}
    for raw, graph in zip(raw_graphs, loaded_graphs, strict=True):
        app_verdicts = [row for row in all_verdicts if row.get("app") == graph.app]
        all_paths.extend(_offset_path_examples(graph, app_verdicts, offsets[graph.app]))
        rule_predictions.update(rule_link(_load_tools(tools_dir, graph.app)))
        for edge in raw["edges"]:
            if edge["type"] == "data" and edge.get("label") is True:
                positive_fields[(edge["src"], edge["dst"])] = edge.get("field")
    if not all_paths:
        raise ValueError("S2 requires both link and path examples")
    all_pairs, all_labels = combined_link_examples(raw_graphs, offsets)

    link_rows: list[dict[str, float]] = []
    rule_rows: list[dict[str, float]] = []
    path_gcn_rows: list[dict[str, float]] = []
    path_mlp_rows: list[dict[str, float]] = []
    link_models = []
    first_train = first_test = 0
    for run_seed in range(seed, seed + seeds):
        train_pairs, train_labels, test_pairs, test_labels = split_link_examples(
            all_pairs, all_labels, seed=run_seed
        )
        encoder, head, link_result = train_link(
            combined,
            train_pairs,
            train_labels,
            test_pairs=test_pairs,
            test_labels=test_labels,
            seed=run_seed,
            epochs=epochs,
        )
        link_models.append((encoder, head))
        link_rows.append(link_result)
        predicted_rule = np.asarray(
            [
                (combined.node_ids[src], combined.node_ids[dst]) in rule_predictions
                for src, dst in test_pairs
            ],
            dtype=np.float64,
        )
        rule_rows.append(classification_metrics(test_labels, predicted_rule))

        train_paths, test_paths = split_by_session(all_paths, seed=run_seed)
        if run_seed == seed:
            first_train, first_test = len(train_paths), len(test_paths)
        _, _, gcn_result = train_path(
            combined, train_paths, test_paths, seed=run_seed, epochs=epochs
        )
        _, mlp_result = mlp_path(combined, train_paths, test_paths, seed=run_seed, epochs=epochs)
        path_gcn_rows.append(gcn_result)
        path_mlp_rows.append(mlp_result)

    positive_pairs = np.asarray(
        [
            (combined.node_ids.index(src), combined.node_ids.index(dst))
            for src, dst in positive_fields
        ],
        dtype=np.int64,
    )
    positive_scores = np.mean(
        [predict_links(combined, encoder, head, positive_pairs) for encoder, head in link_models],
        axis=0,
    )
    recovered = [
        {"src": src, "dst": dst, "field": positive_fields[(src, dst)]}
        for (src, dst), probability in zip(positive_fields, positive_scores, strict=True)
        if (src, dst) not in rule_predictions and probability >= 0.5
    ]

    added_by_app: dict[str, int] = {}
    for path, raw, graph in zip(graph_paths, raw_graphs, loaded_graphs, strict=True):
        candidate_pairs, candidate_ids = _all_absent_pairs(raw, offsets[graph.app])
        scores = np.mean(
            [
                predict_links(combined, encoder, head, candidate_pairs)
                for encoder, head in link_models
            ],
            axis=0,
        )
        predictions = [
            {
                "src": src,
                "dst": dst,
                "type": "data",
                "evidence": "gnn",
                "confidence": float(probability),
                "label": None,
            }
            for (src, dst), probability in zip(candidate_ids, scores, strict=True)
            if probability >= 0.5
        ]
        added_by_app[graph.app] = append_gnn_edges(raw, predictions)
        write_json(path, raw)

    rule_mean = _mean_metrics(rule_rows)
    metrics = {
        "n_train": first_train,
        "n_test": first_test,
        "link": {
            "rule": {"p": rule_mean["p"], "r": rule_mean["r"]},
            "gcn": _mean_metrics(link_rows),
        },
        "path": {"mlp": _mean_metrics(path_mlp_rows), "gcn": _mean_metrics(path_gcn_rows)},
        "recovered_edges": recovered,
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "metrics.json", metrics)
    finished_at = datetime.now(UTC)
    write_json(
        output / "run.json",
        {
            "git_sha": _git_sha(),
            "args": {
                "graphs": str(graph_dir),
                "verdicts": str(verdict_dir),
                "out": str(output),
                "tools": str(tools_dir),
                "seed": seed,
                "seeds": seeds,
                "epochs": epochs,
            },
            "hyperparameters": {
                "hidden": 64,
                "dropout": 0.2,
                "learning_rate": 0.01,
                "test_fraction": 0.3,
            },
            "n_verdicts": len(all_verdicts),
            "gnn_edges_added": added_by_app,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
        },
    )
    return metrics


def main(
    graphs: Annotated[Path, typer.Option("--graphs")] = Path("results/graphs"),
    verdicts: Annotated[Path, typer.Option("--verdicts")] = Path("results/verdicts"),
    out: Annotated[Path, typer.Option("--out")] = Path("results/s2"),
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    run_experiment(graphs=graphs, verdicts=verdicts, out=out, seed=seed)


if __name__ == "__main__":
    typer.run(main)
