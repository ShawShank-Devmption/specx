"""Deterministic synthetic metadata/selector corruption without executing anything.

Mutated tool copies and canned observations are augmentation data, never benchmark
episodes or accepted patches. Unsupported mutation kinds are not fabricated.
"""

import random
from copy import deepcopy
from typing import Any

from specx.client.schemas import validate
from specx.optim.bundle_records import FailureBundle, Mutation
from specx.optim.bundle_trace import aria_diff, transcript_tail


def _eligible(tool: dict[str, Any], mutation: Mutation) -> bool:
    if mutation == "misleading_description":
        return True
    if mutation == "renamed_param":
        return bool(tool["input_schema"].get("properties"))
    handler = tool["handler"]
    return handler["kind"] == "ui" and any(
        selector and selector in handler["code"] for selector in handler.get("selectors", [])
    )


def _mutate(
    tool: dict[str, Any], mutation: Mutation, rng: random.Random
) -> tuple[dict[str, Any], str, str]:
    changed = deepcopy(tool)
    if mutation == "misleading_description":
        changed["description"] = (
            "This tool only lists information and never changes application state."
            if tool["risk_level"] != "read"
            else "Use this tool to delete records and submit a payment."
        )
        return (
            changed,
            "wrong_tool",
            "Synthetic misleading description caused the wrong action to be selected.",
        )
    if mutation == "renamed_param":
        properties = changed["input_schema"]["properties"]
        old = rng.choice(sorted(properties))
        new = f"synthetic_{old}"
        while new in properties:
            new = f"synthetic_{new}"
        properties[new] = properties.pop(old)
        changed["input_schema"]["required"] = [
            new if name == old else name for name in changed["input_schema"].get("required", [])
        ]
        return (
            changed,
            "bad_args",
            f"Synthetic schema renamed {old} to {new}; the unchanged handler still expects {old}.",
        )
    handler = changed["handler"]
    old = rng.choice(
        sorted(
            selector
            for selector in handler["selectors"]
            if selector and selector in handler["code"]
        )
    )
    new = "[data-testid=synthetic-missing-selector]"
    suffix = 0
    while new in handler["code"]:
        suffix += 1
        new = f"[data-testid=synthetic-missing-selector-{suffix}]"
    handler["selectors"] = [
        new if selector == old else selector for selector in handler["selectors"]
    ]
    handler["code"] = handler["code"].replace(old, new)
    return (
        changed,
        "handler_error",
        f"Synthetic selector {new} does not match the intended element ({old}).",
    )


def synthetic_failures(tools: list[dict[str, Any]], n: int, seed: int) -> list[FailureBundle]:
    if type(n) is not int or n < 0 or type(seed) is not int:
        raise ValueError("n must be a non-negative integer and seed must be an integer")
    for tool in tools:
        validate("tool_definition", tool)
    ordered = sorted(tools, key=lambda tool: tool["tool_id"])
    if len({tool["tool_id"] for tool in ordered}) != len(ordered):
        raise ValueError("Synthetic tool IDs must be unique")
    if not ordered and n:
        raise ValueError("At least one tool is required for synthetic failures")
    if n == 0:
        return []
    rng = random.Random(seed)
    kinds: list[Mutation] = ["misleading_description", "renamed_param", "broken_selector"]
    candidates = {kind: [tool for tool in ordered if _eligible(tool, kind)] for kind in kinds}
    available = [kind for kind in kinds if candidates[kind]]
    bundles = []
    for index in range(n):
        kind = available[index % len(available)]
        tool, reason, explanation = _mutate(rng.choice(candidates[kind]), kind, rng)
        before = '- status "Synthetic task pending"'
        after = f'- alert "{explanation}"'
        transcript: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": "Synthetic failure demonstration. No browser or model was executed.",
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "synthetic_call", "name": tool["name"], "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "synthetic_call",
                        "is_error": True,
                        "content": explanation,
                    }
                ],
            },
        ]
        bundles.append(
            FailureBundle(
                trial_id=f"synthetic.{tool['tool_id']}.s{seed}.{index:04}",
                task_id=f"{tool['app']}.synthetic",
                tool_ids=[tool["tool_id"]],
                tools=[tool],
                transcript_tail=transcript_tail(transcript),
                verdicts=[],
                aria_before=before,
                aria_after=after,
                dom_diff=aria_diff(before, after),
                network_log=[],
                screenshot_b64=None,
                failure_reason=reason,
                split="train",
                synthetic=True,
                synthetic_mutation=kind,
            )
        )
    return bundles
