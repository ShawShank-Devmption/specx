from copy import deepcopy
from pathlib import Path

import numpy as np

from specx.client.io import read_json
from specx.client.schemas import validate
from specx.safety.s2.dataset import GraphData
from specx.safety.s2.run import (
    _all_absent_pairs,
    append_gnn_edges,
    combine_graphs,
    combined_link_examples,
    split_link_examples,
)


def test_combine_graphs_offsets_edges_and_node_indices() -> None:
    first = GraphData(
        app="one",
        node_ids=["one.a", "one.b"],
        x=np.zeros((2, 9)),
        edge_index=np.asarray([[0], [1]]),
        edge_type=np.asarray([2]),
    )
    second = GraphData(
        app="two",
        node_ids=["two.a", "two.b"],
        x=np.ones((2, 9)),
        edge_index=np.asarray([[1], [0]]),
        edge_type=np.asarray([1]),
    )

    combined, offsets = combine_graphs([first, second])

    assert offsets == {"one": 0, "two": 2}
    assert combined.node_ids == ["one.a", "one.b", "two.a", "two.b"]
    assert combined.edge_index.tolist() == [[0, 3], [1, 2]]
    assert combined.edge_type.tolist() == [2, 1]


def test_split_link_examples_is_stratified_and_disjoint() -> None:
    pairs = np.asarray([[0, 1], [1, 2], [0, 2], [2, 0]], dtype=np.int64)
    labels = np.asarray([1, 1, 0, 0], dtype=np.int64)

    train_pairs, train_labels, test_pairs, test_labels = split_link_examples(
        pairs, labels, frac=0.5, seed=7
    )

    assert sorted(train_labels.tolist()) == [0, 1]
    assert sorted(test_labels.tolist()) == [0, 1]
    assert {tuple(pair) for pair in train_pairs}.isdisjoint({tuple(pair) for pair in test_pairs})


def test_combined_link_examples_can_use_cross_app_non_edges() -> None:
    def dense_graph(app: str) -> dict:
        node_ids = [f"{app}.a", f"{app}.b"]
        return {
            "app": app,
            "nodes": [{"id": node_id} for node_id in node_ids],
            "edges": [
                {"src": source, "dst": target, "type": "data", "label": True}
                for source in node_ids
                for target in node_ids
                if source != target
            ],
        }

    pairs, labels = combined_link_examples(
        [dense_graph("one"), dense_graph("two")], {"one": 0, "two": 2}
    )

    negatives = pairs[labels == 0]
    assert len(pairs[labels == 1]) == len(negatives) == 4
    assert all((source < 2) != (target < 2) for source, target in negatives)

    absent, ids = _all_absent_pairs(dense_graph("one"), 0)
    assert absent.shape == (0, 2)
    assert ids == []


def test_append_gnn_edges_is_schema_valid_and_idempotent() -> None:
    fixture = Path(__file__).parents[3] / "fixtures" / "graphs" / "shop.graph.json"
    graph = deepcopy(read_json(fixture))
    predictions = [
        {
            "src": "shop.list_products",
            "dst": "shop.view_cart",
            "type": "data",
            "evidence": "gnn",
            "confidence": 0.75,
            "label": None,
        }
    ]

    assert append_gnn_edges(graph, predictions) == 1
    assert append_gnn_edges(graph, predictions) == 0
    assert sum(edge["evidence"] == "gnn" for edge in graph["edges"]) == 1
    validate("workflow_graph", graph)
