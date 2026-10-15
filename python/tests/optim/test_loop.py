import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from specx.client import FakeSandbox
from specx.client.io import read_json, read_jsonl, write_json
from specx.client.paths import contracts_path, repo_root, tools_path, trials_path
from specx.evalx.llm import BudgetExceededError, FakeLLM
from specx.optim.budget import BudgetedLLM
from specx.optim.bundles import synthetic_failures
from specx.optim.loop import app, run_optimisation
from specx.optim.reviser import Arm, propose


def response(name: str, args: dict) -> dict:
    return {
        "stop_reason": "tool_use",
        "usage": {},
        "content": [{"type": "tool_use", "id": "call", "name": name, "input": args}],
    }


def text_response(text: str = "Use the correct product id from the catalogue.") -> dict:
    return {"stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": text}]}


class MetadataAwareLLM(FakeLLM):
    """Deterministic test policy reacts to metadata, not trial order or revision ids."""

    def __init__(self) -> None:
        super().__init__([], model="offline-agent")

    def create(self, **kwargs: Any) -> dict:
        if len(kwargs["messages"]) > 1:
            result = response("finish", {"summary": "Done"})
        else:
            tool = next(tool for tool in kwargs["tools"] if tool["name"] == "add_to_cart")
            product_id = 2 if "correct product id" in tool["description"] else 1
            result = response("add_to_cart", {"product_id": product_id, "qty": 1})
        self._responses.append(result)
        return super().create(**kwargs)


class ScreenshotSandbox(FakeSandbox):
    """Add an explicit fixture image to exercise trace-to-reviser/export wiring."""

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]:
        result = super().state(session_id, screenshot=screenshot)
        if screenshot:
            result["screenshot_b64"] = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
            )
        return result


@pytest.mark.parametrize("arms", [[Arm.text_trace], list(Arm)])
def test_fake_loop_converges_and_preserves_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arms: list[Arm]
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    write_json(tools_path("shop"), tools)
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )
    agent = MetadataAwareLLM()
    structured = json.dumps(
        {
            "ops": [
                {
                    "op": "set_description",
                    "value": "Use the correct product id from the catalogue.",
                    "rationale": "Clarify selection",
                }
            ]
        }
    )
    reviser = FakeLLM(
        [text_response() if arm == Arm.text_trace else text_response(structured) for arm in arms],
        model="offline-reviser",
    )
    metrics = run_optimisation(
        apps=["shop"],
        arms=arms,
        llm=agent,
        reviser=reviser,
        trials=10,
        max_iters=2,
        task_ids=["shop.t02"],
        client_factory=ScreenshotSandbox,
    )
    row = metrics["apps"]["shop"]["text_trace"]
    assert metrics["execution"] == "test_double"
    assert row["accepted"] == row["proposed"] == 1
    assert row["iterations_to_convergence"] <= 2 and row["stop_reason"] == "no_failures"
    assert row["success_by_iter"] == [0.0, 1.0]
    optimised = read_json(tools_path("shop", "optimised.text_trace"))
    assert optimised[1]["metadata_revision"] == 1 and tools[1]["metadata_revision"] == 0
    baseline = read_jsonl(trials_path("gate_shop_baseline"))
    candidate = read_jsonl(trials_path("gate_shop_text_trace_1_c0"))
    assert len(baseline) == len(candidate) == 10
    assert set(row["trial_id"] for row in baseline).isdisjoint(row["trial_id"] for row in candidate)
    dataset = read_jsonl(tmp_path / "s4/dataset.jsonl")
    assert len(dataset) == 10 * len(arms) and all(
        row["bundle_without_screenshot"]["split"] == "train" for row in dataset
    )
    assert set(metrics["apps"]["shop"]) == {arm.value for arm in arms}
    assert len(baseline) == 10  # One baseline, not one per arm.
    for arm in arms:
        arm_row = metrics["apps"]["shop"][arm.value]
        assert arm_row["accepted"] == 1 and arm_row["success_by_iter"] == [0.0, 1.0]
        result = read_json(tools_path("shop", f"optimised.{arm.value}"))
        assert result[1]["metadata_revision"] == 1  # Each arm starts at rev zero.
    assert all(row["screenshot_path"] for row in dataset)
    assert all((tmp_path / "s4" / row["screenshot_path"]).exists() for row in dataset)
    if Arm.multimodal_structured in arms:
        content = reviser.calls[-1]["messages"][0]["content"]
        assert [block["type"] for block in content] == ["image", "image", "image", "text"]
    with pytest.raises(FileExistsError):
        run_optimisation(
            apps=["shop"],
            arms=[Arm.text_trace],
            llm=agent,
            reviser=reviser,
            trials=10,
            task_ids=["shop.t02"],
            client_factory=FakeSandbox,
        )


def test_reviser_verbatim_single_unstructured_call_and_train_only() -> None:
    tool = read_json(repo_root() / "fixtures/tools/shop.tools.json")[1]
    bundles = synthetic_failures([tool], n=1, seed=0)
    llm = FakeLLM([text_response("  Replacement description.\n")], model="offline")
    patch = propose(Arm.text_trace, bundles, tool, llm=llm)
    assert patch["ops"][0]["value"] == "  Replacement description.\n"
    assert len(llm.calls) == 1 and llm.calls[0]["output_config"] == {"effort": "high"}
    assert isinstance(llm.calls[0]["messages"][0]["content"], str)
    bundles[0].split = "heldout"
    with pytest.raises(ValueError, match="train-only"):
        propose(Arm.text_trace, bundles, tool, llm=llm)


@pytest.mark.parametrize("stop", ["refusal", "max_tokens", "tool_use"])
def test_incomplete_reviser_rejected(stop: str) -> None:
    tool = read_json(repo_root() / "fixtures/tools/shop.tools.json")[1]
    result = text_response()
    result["stop_reason"] = stop
    with pytest.raises(ValueError, match="completed"):
        propose(
            Arm.text_trace,
            synthetic_failures([tool], 1, 0),
            tool,
            llm=FakeLLM([result], model="offline"),
        )


def test_cli_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY" in result.output


def test_rejected_candidate_retains_revision_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    write_json(tools_path("shop"), tools)
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )
    metrics = run_optimisation(
        apps=["shop"],
        arms=[Arm.text_trace],
        llm=MetadataAwareLLM(),
        reviser=FakeLLM([text_response("An unhelpful replacement description.")], model="offline"),
        trials=10,
        max_iters=2,
        task_ids=["shop.t02"],
        client_factory=FakeSandbox,
    )
    row = metrics["apps"]["shop"]["text_trace"]
    assert row["accepted"] == 0 and row["rejected"]["no_improvement"] == 1
    assert row["stop_reason"] == "no_accepted_patch"
    assert read_json(tools_path("shop", "optimised.text_trace")) == tools[:2]
    assert not (tmp_path / "s4/dataset.jsonl").exists()


def test_agent_and_reviser_share_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECX_BUDGET_USD", "1")
    agent = FakeLLM([text_response()], model="offline-agent")
    reviser = FakeLLM([text_response()], model="offline-reviser")
    agent.spent_usd = 0.6
    reviser.spent_usd = 0.5
    guarded = BudgetedLLM(reviser, (agent, reviser))
    with pytest.raises(BudgetExceededError, match="Combined"):
        guarded.create(model=reviser.model)
    assert not reviser.calls
