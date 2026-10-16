import json
from pathlib import Path

import numpy as np

from specx.safety.s2.dataset import (
    NODE_FEATS,
    PathExample,
    link_examples,
    load_graph,
    path_examples,
    split_by_session,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_PATH = REPO_ROOT / "fixtures" / "graphs" / "shop.graph.json"


def test_load_graph_uses_only_confirmed_non_rule_edges() -> None:
    graph = load_graph(GRAPH_PATH)

    assert graph.app == "shop"
    assert graph.x.shape == (5, NODE_FEATS)
    assert graph.edge_index.shape == (2, 3)
    assert set(graph.node_ids) == {
        "shop.list_products",
        "shop.add_to_cart",
        "shop.view_cart",
        "shop.remove_from_cart",
        "shop.place_order",
    }
    place_order = graph.node_ids.index("shop.place_order")
    assert graph.x[place_order].tolist() == [0.0, 0.0, 0.0, 1.0, 2.0, 0.0, 4.0, 1.0, 0.42]


def test_link_examples_balance_positives_without_sampling_existing_edges() -> None:
    raw = json.loads(GRAPH_PATH.read_text())

    pairs, labels = link_examples(raw)

    positives = {
        (raw["nodes"][src]["id"], raw["nodes"][dst]["id"])
        for (src, dst), label in zip(pairs.tolist(), labels.tolist(), strict=True)
        if label == 1
    }
    assert positives == {
        ("shop.list_products", "shop.add_to_cart"),
        ("shop.view_cart", "shop.remove_from_cart"),
    }
    assert labels.tolist().count(1) == labels.tolist().count(0) == 2
    existing = {(edge["src"], edge["dst"]) for edge in raw["edges"]}
    negatives = {
        (raw["nodes"][src]["id"], raw["nodes"][dst]["id"])
        for (src, dst), label in zip(pairs.tolist(), labels.tolist(), strict=True)
        if label == 0
    }
    assert not negatives & existing
    assert all(src != dst for src, dst in negatives)


def test_session_disjoint_split() -> None:
    examples = [
        PathExample(
            prefix=[0],
            target=1,
            mutation=0.0,
            label=float(index % 2),
            session_id=f"session-{index // 2}",
        )
        for index in range(12)
    ]

    train, test = split_by_session(examples, frac=0.3, seed=7)

    train_sessions = {example.session_id for example in train}
    test_sessions = {example.session_id for example in test}
    assert train and test
    assert train_sessions.isdisjoint(test_sessions)
    assert train_sessions | test_sessions == {f"session-{index}" for index in range(6)}


def test_path_examples_map_prefix_target_and_violation_label() -> None:
    graph = load_graph(GRAPH_PATH)
    verdicts = [
        {
            "session_id": "session-a",
            "tool_id": "shop.add_to_cart",
            "sequence_prefix": ["shop.list_products"],
            "args": {"product_id": 1, "qty": 1},
            "source": "f1",
            "violations": [],
        },
        {
            "session_id": "session-a",
            "tool_id": "shop.add_to_cart",
            "sequence_prefix": ["shop.list_products"],
            "args": {"product_id": 2, "qty": 99},
            "source": "s1",
            "violations": [{"severity": "high"}],
        },
    ]

    examples = path_examples(graph, verdicts)

    assert len(examples) == 2
    assert examples[0].prefix == [graph.node_ids.index("shop.list_products")]
    assert examples[0].target == graph.node_ids.index("shop.add_to_cart")
    assert examples[0].mutation == 0.0
    assert examples[1].mutation == 1.0
    assert examples[1].label == 1.0
    assert np.asarray([example.label for example in examples]).tolist() == [0.0, 1.0]
