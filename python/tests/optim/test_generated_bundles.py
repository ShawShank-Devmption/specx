"""Offline integration from a generated-condition run to optimisation evidence."""

from pathlib import Path

import pytest

from specx.client import FakeSandbox
from specx.client.io import read_json, read_jsonl, write_json
from specx.client.paths import contracts_path, repo_root, tools_path, traces_dir, trials_path
from specx.evalx.conditions import Condition
from specx.evalx.llm import FakeLLM
from specx.evalx.run import run_benchmark
from specx.optim.bundles import harvest


def test_generated_runner_persists_quarantine_calls_and_harvests_unsafe_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path / "results"))
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[1]["status"] = "quarantined"
    write_json(tools_path("shop"), tools)
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )
    llm = FakeLLM(
        [
            {
                "stop_reason": "tool_use",
                "usage": {},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "a",
                        "name": "add_to_cart",
                        "input": {"product_id": 2, "qty": 1},
                    }
                ],
            },
            {
                "stop_reason": "tool_use",
                "usage": {},
                "content": [
                    {"type": "tool_use", "id": "b", "name": "finish", "input": {"summary": "Done"}}
                ],
            },
        ],
        model="offline-agent",
    )
    metrics = run_benchmark(
        apps=["shop"],
        conditions=[Condition.generated],
        trials=1,
        split="train",
        task_ids=["shop.t02"],
        workers=1,
        out=tmp_path / "metadata",
        llm=llm,
        client_factory=FakeSandbox,
    )
    assert metrics["execution"] == "test_double"
    row = read_jsonl(trials_path("generated"))[0]
    assert row["success"] and row["quarantined_tool_calls"] == 1
    bundles = harvest(trials_path("generated"), traces_dir(), tools, split="train")
    assert len(bundles) == 1 and bundles[0].tool_ids == ["shop.add_to_cart"]
    assert bundles[0].failure_reason == "policy_violation" and not bundles[0].synthetic
