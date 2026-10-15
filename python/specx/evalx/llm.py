"""Frozen Anthropic Messages adapter and a scripted, network-free test double.

The real adapter owns a shared spend ledger; cached input is conservatively priced
at the documented uncached rate. Detailed cache usage remains available in traces.
"""

import math
import os
import sys
from copy import deepcopy
from threading import Lock
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from specx.client.pricing import cost_usd


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    stop_reason: str
    content: list[dict[str, Any]]
    usage: Usage


class AgentLLM(Protocol):
    @property
    def model(self) -> str: ...

    def create(self, **kwargs: Any) -> dict[str, Any]: ...

    def episode_finished(self) -> None: ...


def _agent_model() -> str:
    model = os.environ.get("SPECX_AGENT_MODEL", "").strip()
    if not model:
        raise ValueError("Set SPECX_AGENT_MODEL before creating the frozen evaluation agent")
    return model


class BudgetExceededError(RuntimeError):
    pass


class AnthropicLLM:
    def __init__(self, *, sdk: Any = None, model: str | None = None) -> None:
        # Reviser callers pass SPECX_GEN_MODEL explicitly; evaluation defaults stay frozen.
        self._model = model or _agent_model()
        self.limit_usd = float(os.environ.get("SPECX_BUDGET_USD", "60"))
        if not math.isfinite(self.limit_usd) or self.limit_usd < 0:
            raise ValueError("SPECX_BUDGET_USD must be a finite non-negative amount")
        self.spent_usd = 0.0
        self.episodes = 0
        self._lock = Lock()
        self._owns_sdk = sdk is None
        if sdk is None:
            from anthropic import Anthropic

            sdk = Anthropic()
        self._sdk = sdk

    @property
    def model(self) -> str:
        return self._model

    def _check_budget(self) -> None:
        if self.spent_usd >= self.limit_usd:
            raise BudgetExceededError(
                f"SPECX_BUDGET_USD exhausted: ${self.spent_usd:.4f} / ${self.limit_usd:.2f}"
            )

    def create(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("model") != self.model:
            raise ValueError("Evaluation model must remain frozen")
        with self._lock:
            self._check_budget()
        response = self._sdk.messages.create(**kwargs)
        record = ModelResponse.model_validate(
            response.model_dump(mode="json", exclude_none=True)
        ).model_dump()
        usage = Usage.model_validate(record["usage"])
        with self._lock:
            self.spent_usd += cost_usd(
                self.model,
                usage.input_tokens
                + usage.cache_creation_input_tokens
                + usage.cache_read_input_tokens,
                usage.output_tokens,
            )
            self._check_budget()
        return record

    def episode_finished(self) -> None:
        with self._lock:
            self.episodes += 1
            episodes, spent = self.episodes, self.spent_usd
        if episodes % 50 == 0:
            print(
                f"SpecX: {episodes} episodes; estimated cumulative spend ${spent:.4f}",
                file=sys.stderr,
            )

    def close(self) -> None:
        if self._owns_sdk:
            self._sdk.close()


class FakeLLM:
    """Return scripted Messages-shaped dictionaries and preserve request snapshots."""

    def __init__(self, responses: list[dict[str, Any]], *, model: str | None = None) -> None:
        self.model = model or _agent_model()
        self._responses = deepcopy(responses)
        self.calls: list[dict[str, Any]] = []
        self.episodes = 0

    def create(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("model") != self.model:
            raise ValueError("Evaluation model must remain frozen")
        if len(self.calls) >= len(self._responses):
            raise RuntimeError("FakeLLM script exhausted")
        response = self._responses[len(self.calls)]
        self.calls.append(deepcopy(kwargs))
        return ModelResponse.model_validate(response).model_dump()

    def episode_finished(self) -> None:
        self.episodes += 1
