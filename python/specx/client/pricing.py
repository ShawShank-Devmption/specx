"""Estimate token spend using the build plan's rates, not a live price feed.

Unknown model IDs fail rather than silently undercounting the experiment budget.
"""

from types import MappingProxyType

PRICES = MappingProxyType({"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)})


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must be non-negative")
    if model not in PRICES:
        raise ValueError(f"Unknown model price: {model!r}")
    input_rate, output_rate = PRICES[model]
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
