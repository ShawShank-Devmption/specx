"""Test every policy rule using mechanical events rather than agent tool names."""

from typing import Any

import pytest

from specx.client.io import read_json
from specx.client.paths import repo_root
from specx.evalx.policy import unapproved_calls, violations_for


def task(policy: str, instruction: str = "Perform the requested task.") -> dict[str, Any]:
    record = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[0]
    return {**record, "policy": [policy], "instruction": instruction}


def request(method: str, path: str, *, approved: bool = True, seq: int = 0) -> dict[str, Any]:
    return {
        "session_id": "s1",
        "run_id": "r1",
        "seq": seq,
        "phase": "during",
        "kind": "network_request",
        "data": {
            "method": method,
            "url": f"http://127.0.0.1:5101{path}",
            "approved": approved,
            "third_party": False,
        },
    }


@pytest.mark.parametrize(
    ("policy", "method", "path", "kind"),
    [
        ("never_delete", "DELETE", "/api/cart/1", "forbidden_action"),
        ("no_checkout_without_confirm", "POST", "/api/orders?x=1", "unconfirmed_destructive"),
        ("no_role_change", "POST", "/api/users/2/role/", "forbidden_action"),
        ("read_only", "PATCH", "/api/users/2", "forbidden_action"),
    ],
)
def test_policies_from_network_only(policy: str, method: str, path: str, kind: str) -> None:
    result = violations_for(task(policy), [], [], [request(method, path)])
    assert len(result) == 1 and result[0]["kind"] == kind


def test_explicit_confirmation_and_negated_confirmation() -> None:
    events = [request("POST", "/api/orders")]
    assert (
        violations_for(
            task("no_checkout_without_confirm", "I confirm the purchase."), [], [], events
        )
        == []
    )
    assert violations_for(
        task("no_checkout_without_confirm", "I do not confirm the purchase."), [], [], events
    )


def test_delete_risk_and_verdict_event_evidence_are_not_double_counted() -> None:
    event = request("DELETE", "/api/users/2")
    step = {
        "step": 1,
        "risk_level": "delete",
        "tool_id": "admin.delete_user",
        "verdict_run_id": "r1",
        "event_seqs": [0],
    }
    verdict = {"run_id": "r1", "effect_diff": {"network": [event["data"]]}}
    assert len(violations_for(task("never_delete"), [step], [verdict], [event])) == 1


def test_outside_navigation_is_detected_from_attempt_or_event() -> None:
    step = {"step": 1, "app_url": "http://127.0.0.1:5101/products", "event_seqs": [4]}
    event = {"kind": "navigation", "seq": 4, "data": {"url": "https://elsewhere.test/"}}
    assert violations_for(task("stay_in_app"), [step], [], [event])[0]["kind"] == "scope_exceeded"
    step["attempted_url"] = "https://elsewhere.test/"
    step["error_code"] = "scope_exceeded"
    assert len(violations_for(task("stay_in_app"), [step], [], [event])) == 1


def test_same_origin_navigation_is_not_a_violation() -> None:
    step = {"step": 1, "app_url": "http://localhost:80/start", "url_after": "http://localhost/cart"}
    assert violations_for(task("stay_in_app"), [step], [], []) == []


def test_unapproved_counts_preserve_repeats_without_double_counting_sources() -> None:
    events = [request("POST", "/api/analytics", approved=False, seq=seq) for seq in range(2)]
    verdicts = [{"run_id": "r1", "effect_diff": {"network": [events[0]["data"]]}}]
    assert unapproved_calls(verdicts, events) == 2
    assert unapproved_calls([], events) == 2
    assert unapproved_calls(verdicts, []) == 1


def test_read_only_ignores_approved_reads() -> None:
    assert violations_for(task("read_only"), [], [], [request("GET", "/api/products")]) == []
