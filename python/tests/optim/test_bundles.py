"""Verify factual failure harvesting and explicitly labelled, pure synthetic injection."""

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from specx.client.io import read_json, read_jsonl, write_json, write_jsonl
from specx.client.paths import repo_root
from specx.optim.bundles import FailureBundle, harvest, synthetic_failures


@pytest.fixture
def evidence(tmp_path: Path) -> tuple[Path, Path, list[dict[str, Any]], dict[str, Any]]:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    verdict = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[1]
    trial = read_jsonl(repo_root() / "fixtures/trials/sample.trials.jsonl")[0]
    trial.update(
        trial_id="shop.t02.generated.s0",
        task_id="shop.t02",
        condition="generated",
        split="train",
        failure_reason="wrong_tool",
        unapproved_calls=1,
    )
    trial["trace_path"] = f"results/traces/{trial['trial_id']}.json"
    trace = {
        "trial_id": trial["trial_id"],
        "task_id": trial["task_id"],
        "app": "shop",
        "condition": "generated",
        "aria_before": '- status "Ready"',
        "aria_after": '- alert "Action failed"',
        "final_screenshot_b64": None,
        "verdicts": [verdict],
        "events": [],
        "step_log": [
            {
                "step": 1,
                "name": "add_to_cart",
                "tool_id": "shop.add_to_cart",
                "invoked": True,
                "verdict_run_id": verdict["run_id"],
                "aria_before": '- status "Ready"',
                "aria_after": '- alert "Action failed"',
                "event_seqs": [],
            }
        ],
        "messages": [{"role": "user", "content": f"message {i}"} for i in range(8)],
    }
    traces = tmp_path / "traces"
    write_json(traces / f"{trial['trial_id']}.json", trace)
    path = tmp_path / "trials.jsonl"
    write_jsonl(path, [trial])
    return path, traces, tools, trace


def test_harvest_fixture_trace_has_real_diff_verdicts_network_and_tool_ids(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    bundles = harvest(path, traces, tools)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.tool_ids == ["shop.add_to_cart"] and len(bundle.tools) == 1
    assert bundle.dom_diff.startswith("--- aria_before")
    assert '- status "Ready"' in bundle.dom_diff and '+- alert "Action failed"' in bundle.dom_diff
    assert bundle.transcript_tail == trace["messages"][-6:]
    assert bundle.network_log == trace["verdicts"][0]["effect_diff"]["network"]
    assert not bundle.synthetic and bundle.split == "train"
    assert FailureBundle.model_validate(bundle.model_dump()) == bundle
    json.dumps(bundle.model_dump(), allow_nan=False)


def test_tool_result_bodies_and_diff_are_bounded_without_editing_source(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["messages"][-1]["content"] = [
        {"type": "tool_result", "tool_use_id": "a", "content": "x" * 9000},
        {
            "type": "tool_result",
            "tool_use_id": "b",
            "content": [{"type": "text", "text": "y" * 9000}],
        },
    ]
    trace["step_log"][0]["aria_after"] = "\n".join(f"changed {i}" for i in range(1000))
    trace_path = traces / f"{trace['trial_id']}.json"
    write_json(trace_path, trace)
    bundle = harvest(path, traces, tools)[0]
    assert len(bundle.dom_diff) <= 4000
    assert all(len(block["content"]) <= 2000 for block in bundle.transcript_tail[-1]["content"])
    assert len(read_json(trace_path)["messages"][-1]["content"][0]["content"]) == 9000


def test_harvest_defaults_to_failures_but_includes_unsafe_successes(evidence: Any) -> None:
    path, traces, tools, _ = evidence
    trial = read_jsonl(path)[0]
    trial.update(success=True, failure_reason="none")
    write_jsonl(path, [trial])
    bundle = harvest(path, traces, tools)[0]
    assert bundle.failure_reason == "policy_violation"
    trial["unapproved_calls"] = 0
    write_jsonl(path, [trial])
    assert harvest(path, traces, tools) == []
    assert len(harvest(path, traces, tools, only_failures=False)) == 1


def test_unchanged_dom_has_empty_diff_not_invented_evidence(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["step_log"][0]["aria_after"] = trace["step_log"][0]["aria_before"]
    write_json(traces / f"{trace['trial_id']}.json", trace)
    assert harvest(path, traces, tools)[0].dom_diff == ""


def test_harvest_retains_split_and_allows_explicit_train_filter(evidence: Any) -> None:
    path, traces, tools, _ = evidence
    trial = read_jsonl(path)[0]
    trial["split"] = "heldout"
    write_jsonl(path, [trial])
    assert harvest(path, traces, tools)[0].split == "heldout"
    assert harvest(path, traces, tools, split="train") == []


def test_missing_or_mismatched_trace_fails_loudly(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    with pytest.raises(FileNotFoundError):
        harvest(path, traces / "missing", tools)
    trace["task_id"] = "shop.t99"
    write_json(traces / f"{trace['trial_id']}.json", trace)
    with pytest.raises(ValueError, match="mismatch"):
        harvest(path, traces, tools)


def test_unknown_explicit_tool_id_is_not_silently_dropped(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["step_log"][0]["tool_id"] = "shop.missing"
    write_json(traces / f"{trace['trial_id']}.json", trace)
    with pytest.raises(ValueError, match="tool"):
        harvest(path, traces, tools)


def test_trace_paths_cannot_escape_the_supplied_directory(evidence: Any) -> None:
    path, traces, tools, _ = evidence
    trial = read_jsonl(path)[0]
    trial["trial_id"] = "../../outside"
    write_jsonl(path, [trial])
    with pytest.raises(ValueError, match="trial_id"):
        harvest(path, traces, tools)


def test_raw_dom_network_evidence_is_preserved_without_verdicts(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["verdicts"] = []
    trace["step_log"] = [
        {"step": 1, "name": "click", "event_seqs": [0], "error_code": "handler_error"}
    ]
    trace["events"] = [
        {
            "session_id": "s1",
            "run_id": "r1",
            "seq": 0,
            "t_ms": 1,
            "phase": "during",
            "kind": "network_request",
            "data": {
                "method": "POST",
                "url": "/api/orders",
                "approved": True,
                "third_party": False,
            },
        }
    ]
    write_json(traces / f"{trace['trial_id']}.json", trace)
    bundle = harvest(path, traces, tools)[0]
    assert bundle.tool_ids == []
    assert bundle.network_log[0]["url"] == "/api/orders"


def test_no_tool_calls_do_not_blame_arbitrary_tools(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace.update(step_log=[], verdicts=[])
    write_json(traces / f"{trace['trial_id']}.json", trace)
    bundle = harvest(path, traces, tools)[0]
    assert bundle.tool_ids == [] and bundle.tools == []


def test_synthetic_bundles_are_seeded_pure_and_do_not_mutate_tools(evidence: Any) -> None:
    _, _, tools, _ = evidence
    before = deepcopy(tools)
    random.seed(42)
    state = random.getstate()
    bundles = synthetic_failures(tools, n=6, seed=3)
    assert bundles == synthetic_failures(list(reversed(tools)), n=6, seed=3)
    assert tools == before and random.getstate() == state
    assert len({bundle.trial_id for bundle in bundles}) == 6
    for bundle in bundles:
        assert bundle.synthetic and bundle.split == "train"
        assert bundle.trial_id.startswith("synthetic.")
        assert bundle.verdicts == [] and bundle.network_log == [] and bundle.screenshot_b64 is None
        assert bundle.dom_diff
        assert FailureBundle.model_validate(bundle.model_dump()) == bundle


def test_synthetic_mutations_cover_available_cases_including_selectors(evidence: Any) -> None:
    _, _, tools, _ = evidence
    ui = deepcopy(tools[1])
    ui["tool_id"] = "shop.ui_add"
    ui["name"] = "ui_add"
    ui["handler"] = {
        "kind": "ui",
        "selectors": ["#add"],
        "code": "async (input) => document.querySelector('#add').click()",
    }
    bundles = synthetic_failures([*tools, ui], n=3, seed=0)
    assert {bundle.synthetic_mutation for bundle in bundles} == {
        "misleading_description",
        "renamed_param",
        "broken_selector",
    }
    broken = next(bundle for bundle in bundles if bundle.synthetic_mutation == "broken_selector")
    assert "#add" not in broken.tools[0]["handler"]["selectors"]
    assert "#add" not in broken.tools[0]["handler"]["code"]


def test_synthetic_empty_and_invalid_inputs(evidence: Any) -> None:
    _, _, tools, _ = evidence
    assert synthetic_failures([], 0, seed=0) == []
    with pytest.raises(ValueError):
        synthetic_failures([], 1, seed=0)
    with pytest.raises(ValueError):
        synthetic_failures(tools, -1, seed=0)


def test_network_evidence_is_not_duplicated_between_verdicts_and_events(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    verdict = trace["verdicts"][0]
    trace["events"] = [
        {
            "session_id": verdict["session_id"],
            "run_id": verdict["run_id"],
            "seq": seq,
            "t_ms": seq,
            "phase": request.get("phase", "during"),
            "kind": "network_request",
            "data": request,
        }
        for seq, request in enumerate(verdict["effect_diff"]["network"])
    ]
    trace["step_log"][0]["event_seqs"] = [event["seq"] for event in trace["events"]]
    write_json(traces / f"{trace['trial_id']}.json", trace)
    assert len(harvest(path, traces, tools)[0].network_log) == len(
        verdict["effect_diff"]["network"]
    )


def test_input_error_does_not_claim_earlier_successful_requests(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    passed = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[0]
    trace["verdicts"] = [passed]
    trace["step_log"] = [
        {
            "step": 2,
            "name": "add_to_cart",
            "tool_id": "shop.add_to_cart",
            "error_code": "bad_args",
            "invoked": False,
            "event_seqs": [],
        }
    ]
    trace["events"] = read_jsonl(repo_root() / "fixtures/events/approved_trace.jsonl")
    write_json(traces / f"{trace['trial_id']}.json", trace)
    assert harvest(path, traces, tools)[0].network_log == []


def test_raw_dom_helper_is_not_matched_to_a_same_named_webmcp_tool(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trial = read_jsonl(path)[0]
    trial["condition"] = trace["condition"] = "raw_dom"
    tools[0]["name"] = "click"
    trace.update(verdicts=[], step_log=[{"step": 1, "name": "click", "event_seqs": []}])
    write_jsonl(path, [trial])
    write_json(traces / f"{trace['trial_id']}.json", trace)
    assert harvest(path, traces, tools)[0].tool_ids == []


def test_screenshot_is_retained_and_invalid_bundles_are_rejected(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["final_screenshot_b64"] = "c2NyZWVuc2hvdA=="
    write_json(traces / f"{trace['trial_id']}.json", trace)
    bundle = harvest(path, traces, tools)[0]
    assert bundle.screenshot_b64 == trace["final_screenshot_b64"]
    with pytest.raises(ValueError, match="tool_ids"):
        FailureBundle.model_validate({**bundle.model_dump(), "tool_ids": []})
    with pytest.raises(ValueError):
        FailureBundle.model_validate({**bundle.model_dump(), "dom_diff": "x" * 4001})


def test_synthetic_generation_never_executes_browser_or_model(
    evidence: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, tools, _ = evidence

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Synthetic augmentation must not execute anything")

    for target in (
        "specx.client.SandboxClient._request",
        "specx.client.FakeSandbox.invoke",
        "specx.evalx.llm.FakeLLM.create",
        "specx.evalx.llm.AnthropicLLM.create",
    ):
        monkeypatch.setattr(target, forbidden)
    assert len(synthetic_failures(tools, n=3, seed=0)) == 3


def test_trace_split_cannot_silently_relabel_heldout_as_train(evidence: Any) -> None:
    path, traces, tools, trace = evidence
    trace["task"] = {"split": "heldout"}
    write_json(traces / f"{trace['trial_id']}.json", trace)
    with pytest.raises(ValueError, match="split mismatch"):
        harvest(path, traces, tools, split="train")
