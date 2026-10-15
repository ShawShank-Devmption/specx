"""Schema-aware argument mutations for the S1 adversarial fuzzer."""

import copy
from typing import Any

import numpy as np

MUTATIONS = [
    "valid",
    "boundary_max",
    "boundary_zero",
    "wrong_type",
    "missing_required",
    "unknown_id",
    "replay_last",
    "concurrent_x2",
]


def _choose(candidates: list[str], rng: np.random.Generator) -> str | None:
    if not candidates:
        return None
    return candidates[int(rng.integers(0, len(candidates)))]


def _wrong_value(schema: dict[str, Any]) -> Any:
    value_type = schema.get("type")
    if value_type == "string":
        return 0
    if value_type in {"integer", "number"}:
        return "not-a-number"
    if value_type == "boolean":
        return "not-a-boolean"
    if value_type == "array":
        return {}
    return []


def mutate(
    tool: dict[str, Any],
    valid_args: dict[str, Any],
    mutation: str,
    rng: np.random.Generator,
) -> tuple[dict[str, Any], str]:
    if mutation not in MUTATIONS:
        raise ValueError(f"unknown mutation: {mutation}")

    args = copy.deepcopy(valid_args)
    if mutation in {"valid", "replay_last", "concurrent_x2"}:
        return args, mutation

    schema = tool.get("input_schema", {})
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return args, "valid"

    if mutation == "boundary_max":
        candidates = [
            name
            for name, value in properties.items()
            if isinstance(value, dict) and value.get("type") == "integer"
        ]
        field = _choose(candidates, rng)
        if field is None:
            return args, "valid"
        field_schema = properties[field]
        args[field] = int(field_schema.get("maximum", 2**31 - 1))
    elif mutation == "boundary_zero":
        candidates = [
            name
            for name, value in properties.items()
            if isinstance(value, dict) and value.get("type") in {"integer", "number"}
        ]
        field = _choose(candidates, rng)
        if field is None:
            return args, "valid"
        args[field] = 0
    elif mutation == "wrong_type":
        field = _choose(list(properties), rng)
        if field is None:
            return args, "valid"
        field_schema = properties[field]
        args[field] = _wrong_value(field_schema if isinstance(field_schema, dict) else {})
    elif mutation == "missing_required":
        required = [name for name in schema.get("required", []) if name in args]
        field = _choose(required, rng)
        if field is None:
            return args, "valid"
        del args[field]
    elif mutation == "unknown_id":
        candidates = [
            name
            for name, value in properties.items()
            if name.endswith("_id") and isinstance(value, dict) and value.get("type") == "integer"
        ]
        field = _choose(candidates, rng)
        if field is None:
            return args, "valid"
        args[field] = 2**31 - 1
    return args, mutation
