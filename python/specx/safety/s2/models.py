"""Neural components for S2 graph link and path-risk prediction."""

from typing import cast

import torch
from torch import nn
from torch_geometric.nn import GCNConv

from specx.safety.s2.dataset import NODE_FEATS


class GCNEncoder(nn.Module):
    def __init__(self, in_features: int = NODE_FEATS, hidden: int = 64) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_features, hidden)
        self.conv2 = GCNConv(hidden, hidden)
        self.dropout = nn.Dropout(0.2)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        hidden = torch.relu(self.conv1(x, edge_index))
        hidden = self.dropout(hidden)
        return cast(torch.Tensor, self.conv2(hidden, edge_index))


class LinkHead(nn.Module):
    def forward(self, embeddings: torch.Tensor, pairs: torch.Tensor) -> torch.Tensor:
        src = embeddings[pairs[:, 0]]
        dst = embeddings[pairs[:, 1]]
        return torch.sigmoid((src * dst).sum(dim=1))


class PathHead(nn.Module):
    def __init__(self, embedding_features: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(embedding_features * 2 + 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self.network(features).squeeze(1))
