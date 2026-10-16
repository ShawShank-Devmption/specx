import numpy as np

from specx.safety.s2.baselines import mlp_path, rule_link
from specx.safety.s2.dataset import GraphData, PathExample
from specx.safety.s2.models import GCNEncoder, LinkHead
from specx.safety.s2.train import predict_links, train_link, train_path


def toy_graph() -> GraphData:
    x = np.zeros((4, 9), dtype=np.float64)
    x[:, :4] = np.eye(4)
    x[:, 4] = np.arange(4)
    return GraphData(
        app="toy",
        node_ids=[f"toy.node_{index}" for index in range(4)],
        x=x,
        edge_index=np.asarray([[0, 1, 2, 3], [1, 0, 3, 2]], dtype=np.int64),
        edge_type=np.asarray([2, 2, 2, 2], dtype=np.int64),
    )


def test_rule_link_matches_output_leaf_to_input_name() -> None:
    tools = [
        {
            "tool_id": "toy.source",
            "output_schema": {
                "type": "object",
                "properties": {
                    "item": {"type": "object", "properties": {"id": {"type": "integer"}}}
                },
            },
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "tool_id": "toy.target",
            "output_schema": {"type": "object", "properties": {}},
            "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}},
        },
    ]

    assert rule_link(tools) == {("toy.source", "toy.target")}


def test_link_gcn_overfits_twenty_examples() -> None:
    graph = toy_graph()
    base_pairs = np.asarray([[0, 1], [2, 3], [0, 2], [1, 3]], dtype=np.int64)
    base_labels = np.asarray([1, 1, 0, 0], dtype=np.int64)
    pairs = np.tile(base_pairs, (5, 1))
    labels = np.tile(base_labels, 5)

    _, _, result = train_link(
        graph,
        pairs,
        labels,
        test_pairs=pairs,
        test_labels=labels,
        seed=3,
        epochs=200,
    )

    assert result["auc"] == 1.0


def test_predict_links_accepts_an_empty_pair_batch() -> None:
    probabilities = predict_links(
        toy_graph(), GCNEncoder(), LinkHead(), np.empty((0, 2), dtype=np.int64)
    )

    assert probabilities.shape == (0,)


def test_path_models_overfit_twenty_examples() -> None:
    graph = toy_graph()
    examples = [
        PathExample(
            prefix=[0, 1],
            target=index % 2,
            mutation=float(index % 2),
            label=float(index % 2),
            session_id=f"session-{index}",
        )
        for index in range(20)
    ]

    _, _, gcn = train_path(graph, examples, examples, seed=5, epochs=200)
    _, mlp = mlp_path(graph, examples, examples, seed=5, epochs=200)

    assert gcn["auc"] == 1.0
    assert mlp["auc"] == 1.0
