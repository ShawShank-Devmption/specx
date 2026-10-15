"""One cumulative spend ceiling across the frozen agent and reviser adapters."""

import math
import os
from typing import Any

from specx.evalx.llm import AgentLLM, BudgetExceededError


class BudgetedLLM:
    def __init__(self, llm: AgentLLM, peers: tuple[AgentLLM, ...]) -> None:
        self.llm, self.peers = llm, peers
        self.limit = float(os.environ.get("SPECX_BUDGET_USD", "60"))
        if not math.isfinite(self.limit) or self.limit < 0:
            raise ValueError("SPECX_BUDGET_USD must be finite and non-negative")

    @property
    def model(self) -> str:
        return self.llm.model

    @property
    def spent_usd(self) -> float:
        return float(getattr(self.llm, "spent_usd", 0.0))

    def _check(self) -> None:
        total = sum(float(getattr(peer, "spent_usd", 0.0)) for peer in self.peers)
        if total >= self.limit:
            raise BudgetExceededError(f"Combined optimisation budget exhausted: ${total:.4f}")

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self._check()
        response = self.llm.create(**kwargs)
        self._check()
        return response

    def episode_finished(self) -> None:
        self.llm.episode_finished()
