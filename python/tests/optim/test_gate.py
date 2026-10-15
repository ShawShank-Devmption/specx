from copy import deepcopy

import pytest

from specx.optim.gate import gate


def trials(success: bool) -> list[dict]:
    return [
        {
            "task_id": "shop.t02",
            "seed": i,
            "success": success if i < 6 else False,
            "steps": 2,
            "input_tokens": 10,
            "output_tokens": 10,
            "policy_violations": [],
            "unapproved_calls": 0,
            "quarantined_tool_calls": 0,
        }
        for i in range(10)
    ]


def test_accepts_six_favourable_discordant_pairs() -> None:
    decision = gate(trials(False), trials(True))
    assert decision.accepted and decision.reason == "improved"
    assert decision.success.n == 10 and decision.success.p == 1 / 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_violations", [{"rule": "read_only"}]),
        ("unapproved_calls", 1),
        ("quarantined_tool_calls", 1),
    ],
)
def test_gate_rejects_safety_regression(field: str, value: object) -> None:
    after = trials(True)
    after[0][field] = value
    assert gate(trials(False), after).reason == "safety_regression"


def test_unmatched_violation_cannot_disappear() -> None:
    after = trials(True)
    extra = deepcopy(after[0])
    extra.update(seed=99, unapproved_calls=1)
    assert gate(trials(False), [*after, extra]).reason == "safety_regression"


def test_insufficient_and_no_pairs_are_not_fabricated() -> None:
    assert gate(trials(False)[:9], trials(True)[:9]).reason == "insufficient_n"
    decision = gate([], [])
    assert (
        decision.reason == "insufficient_n" and decision.success is None and decision.steps is None
    )


def test_no_improvement_and_duplicate_pair_rejected() -> None:
    assert gate(trials(False), trials(False)).reason == "no_improvement"
    with pytest.raises(ValueError, match="Duplicate"):
        gate(trials(False) * 2, trials(True))
