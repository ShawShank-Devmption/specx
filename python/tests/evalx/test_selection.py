"""C9 training-only selection and verified/optimised paired-run integration."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from specx.client import FakeSandbox
from specx.client.io import read_json, read_jsonl, write_json
from specx.client.paths import contracts_path, patches_dir, repo_root, stage_dir, tools_path
from specx.evalx.conditions import Condition
from specx.evalx.llm import FakeLLM
from specx.evalx.run import _jobs, run_benchmark
from specx.evalx.selection import select_optimised
from specx.optim.gate import gate
from specx.optim.loop import run_optimisation
from specx.optim.patch import apply_patch
from specx.optim.reviser import Arm


def publish(scores: dict[str, float], accepted: bool = False) -> None:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    write_json(tools_path("shop"), tools)
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )
    metrics = {"execution": "test_double", "apps": {"shop": {}}}
    for arm, score in scores.items():
        candidate = deepcopy(tools[:2])
        revisions = []
        if accepted:
            before = [
                {
                    "task_id": "shop.t02",
                    "seed": seed,
                    "success": False,
                    "steps": 1,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "policy_violations": [],
                    "unapproved_calls": 0,
                    "quarantined_tool_calls": 0,
                }
                for seed in range(10)
            ]
            after = [{**record, "success": record["seed"] < round(score * 10)} for record in before]
            patch = {
                "patch_id": f"patch-{arm}",
                "tool_id": "shop.add_to_cart",
                "base_metadata_revision": 0,
                "source_trial_ids": ["gate_shop_baseline.shop.t02.s0"],
                "modality": arm,
                "model": "offline-reviser",
                "ops": [
                    {
                        "op": "set_description",
                        "value": "Use the correct product id from the catalogue.",
                        "rationale": "Clarify selection",
                    }
                ],
            }
            write_json(patches_dir() / f"shop.{arm}.1.shop.add_to_cart.patch.json", patch)
            candidate[1] = apply_patch(candidate[1], patch)
            revisions = [
                {
                    **gate(before, after).model_dump(mode="json"),
                    "app": "shop",
                    "arm": arm,
                    "iter": 1,
                    "tool_id": "shop.add_to_cart",
                    "patch_id": patch["patch_id"],
                }
            ]
        write_json(tools_path("shop", f"optimised.{arm}"), candidate)
        metrics["apps"]["shop"][arm] = {
            "success_by_iter": [score] if not accepted else [0.0, score],
            "accepted": int(accepted),
            "proposed": int(accepted),
            "revisions": revisions,
        }
    write_json(stage_dir("f2") / "metrics.json", metrics)
    write_json(
        stage_dir("f2") / "run.json",
        {
            "status": "complete",
            "models": {"agent": "offline-agent", "reviser": "offline-reviser"},
            "execution": "test_double",
            "args": {
                "apps": ["shop"],
                "arms": list(scores),
                "task_ids": ["shop.t02"],
                "trials": 10,
                "seed": 0,
            },
        },
    )


@pytest.fixture
def results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    publish({arm.value: 0.0 for arm in Arm})
    return tmp_path


def select(arm: str | None = None) -> tuple[list[dict], object]:
    return select_optimised("shop", model="offline-agent", execution="test_double", arm=arm)


def test_ties_prefer_multimodal_and_zero_acceptance_is_explicit(results: Path) -> None:
    tools, choice = select()
    assert choice.arm == "multimodal_structured" and choice.reason == "best_train_success"
    assert choice.identical_to_verified and choice.no_accepted_patches
    assert tools == read_json(tools_path("shop"))[:2]


def test_train_winner_beats_multimodal_and_override_is_recorded(results: Path) -> None:
    publish(
        {"text_trace": 0.8, "text_structured": 0.6, "multimodal_structured": 0.4}, accepted=True
    )
    tools, choice = select()
    assert choice.arm == "text_trace" and tools[1]["metadata_revision"] == 1
    assert not choice.no_accepted_patches and not choice.identical_to_verified
    _, override = select("text_structured")
    assert override.reason == "explicit_override" and override.arm == "text_structured"


@pytest.mark.parametrize(
    "mutation",
    [
        "failed",
        "model",
        "execution",
        "missing_arm",
        "nan",
        "heldout",
        "missing_patch",
        "changed_tool",
        "false_zero",
    ],
)
def test_rejects_incomplete_or_inconsistent_evidence(results: Path, mutation: str) -> None:
    publish({arm.value: 0.5 for arm in Arm}, accepted=mutation == "missing_patch")
    run = read_json(stage_dir("f2") / "run.json")
    metrics = read_json(stage_dir("f2") / "metrics.json")
    if mutation == "failed":
        run["status"] = "failed"
    elif mutation == "model":
        run["models"]["agent"] = "another-agent"
    elif mutation == "execution":
        run["execution"] = metrics["execution"] = "real"
    elif mutation == "missing_arm":
        del metrics["apps"]["shop"]["text_trace"]
    elif mutation == "nan":
        metrics["apps"]["shop"]["text_trace"]["success_by_iter"] = [None]
    elif mutation == "heldout":
        run["args"]["task_ids"] = ["shop.t01"]
    elif mutation == "missing_patch":
        (patches_dir() / "shop.multimodal_structured.1.shop.add_to_cart.patch.json").unlink()
    elif mutation == "false_zero":
        metrics["apps"]["shop"]["multimodal_structured"]["success_by_iter"] = [0.5, 0.8]
    else:
        tools = read_json(tools_path("shop", "optimised.multimodal_structured"))
        tools[0]["description"] = "Undocumented altered description."
        write_json(tools_path("shop", "optimised.multimodal_structured"), tools)
    write_json(stage_dir("f2") / "run.json", run)
    write_json(stage_dir("f2") / "metrics.json", metrics)
    with pytest.raises((ValueError, FileNotFoundError)):
        select()


def finish_script(n: int) -> list[dict]:
    return [
        {
            "stop_reason": "tool_use",
            "usage": {},
            "content": [
                {
                    "type": "tool_use",
                    "id": "f",
                    "name": "finish",
                    "input": {"summary": "Cannot complete"},
                }
            ],
        }
        for _ in range(n)
    ]


def evaluate(results: Path, llm: FakeLLM, **kwargs: object) -> dict:
    return run_benchmark(
        apps=["shop"],
        conditions=[Condition.verified, Condition.optimised],
        trials=2,
        task_ids=["shop.t07"],
        workers=1,
        llm=llm,
        client_factory=FakeSandbox,
        out=results / "evaluation",
        **kwargs,
    )


def test_paired_heldout_run_records_choice_and_no_gain_note_and_resumes(results: Path) -> None:
    metrics = evaluate(results, FakeLLM(finish_script(4), model="offline-agent"))
    assert metrics["completed"] == 4 and metrics["complete"]
    run = read_json(results / "evaluation/run.json")
    assert run["optimisation_selection"]["shop"]["arm"] == "multimodal_structured"
    assert metrics["optimisation_selection"]["shop"]["no_accepted_patches"]
    assert "optimised == verified" in metrics["notes"][0]
    left, right = (
        read_jsonl(results / "trials/verified.jsonl"),
        read_jsonl(results / "trials/optimised.jsonl"),
    )
    assert {(row["task_id"], row["seed"]) for row in left} == {
        (row["task_id"], row["seed"]) for row in right
    }
    assert {row["tool_set_version"] for row in left} == {row["tool_set_version"] for row in right}
    assert all(row["split"] == "heldout" for row in left + right)
    llm = FakeLLM([], model="offline-agent")
    evaluate(results, llm)
    assert not llm.calls
    with pytest.raises(ValueError, match=r"context|selection"):
        evaluate(results, llm, arm="text_trace")


def test_verified_revision_zero_required(results: Path) -> None:
    tools = read_json(tools_path("shop"))
    tools[0]["metadata_revision"] = 1
    write_json(tools_path("shop"), tools)
    with pytest.raises(ValueError, match=r"revision.zero"):
        _jobs(["shop"], [Condition.verified], 5, 0, "heldout", None, None)


def test_default_c9_design_has_one_hundred_paired_jobs(results: Path) -> None:
    tools = read_json(tools_path("shop"))
    admin = deepcopy(tools)
    for tool in admin:
        tool["app"] = "admin"
        tool["tool_id"] = tool["tool_id"].replace("shop.", "admin.")
    write_json(tools_path("admin"), admin)
    write_json(contracts_path("admin"), [])
    selected = {"shop": tools[:2], "admin": admin[:2]}
    jobs = _jobs(
        ["shop", "admin"],
        [Condition.verified, Condition.optimised],
        5,
        0,
        "heldout",
        None,
        None,
        selected,
    )
    assert len(jobs) == 100
    for app in ("shop", "admin"):
        cohorts = [
            {
                (job.task.task_id, job.seed)
                for job in jobs
                if job.task.app == app and job.condition == condition
            }
            for condition in (Condition.verified, Condition.optimised)
        ]
        assert cohorts[0] == cohorts[1] and len(cohorts[0]) == 25


def test_real_f2_output_flows_into_heldout_evaluation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    write_json(tools_path("shop"), read_json(repo_root() / "fixtures/tools/shop.tools.json"))
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )

    class MetadataAgent(FakeLLM):
        def create(self, **kwargs: Any) -> dict:
            if len(kwargs["messages"]) > 1:
                response = finish_script(1)[0]
            else:
                description = next(
                    tool["description"] for tool in kwargs["tools"] if tool["name"] == "add_to_cart"
                )
                response = {
                    "stop_reason": "tool_use",
                    "usage": {},
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "a",
                            "name": "add_to_cart",
                            "input": {
                                "product_id": 2 if "correct product id" in description else 1,
                                "qty": 1,
                            },
                        }
                    ],
                }
            self._responses.append(response)
            return super().create(**kwargs)

    description = "Use the correct product id from the catalogue."
    responses = [
        {
            "stop_reason": "end_turn",
            "usage": {},
            "content": [
                {
                    "type": "text",
                    "text": description
                    if arm == Arm.text_trace
                    else json.dumps(
                        {
                            "ops": [
                                {
                                    "op": "set_description",
                                    "value": description,
                                    "rationale": "Clarify selection",
                                }
                            ]
                        }
                    ),
                }
            ],
        }
        for arm in Arm
    ]
    run_optimisation(
        apps=["shop"],
        arms=list(Arm),
        llm=MetadataAgent([], model="offline-agent"),
        reviser=FakeLLM(responses, model="offline-reviser"),
        trials=10,
        max_iters=2,
        task_ids=["shop.t02"],
        client_factory=FakeSandbox,
    )
    metrics = evaluate(tmp_path, FakeLLM(finish_script(4), model="offline-agent"))
    choice = metrics["optimisation_selection"]["shop"]
    assert choice["arm"] == "multimodal_structured" and choice["accepted_patches"] == 1
    assert not choice["identical_to_verified"] and not choice["no_accepted_patches"]
    assert metrics["conditions"]["verified"]["shop"]["n"] == 2
    assert metrics["conditions"]["optimised"]["shop"]["n"] == 2


def test_changed_training_evidence_refuses_resume_even_when_tools_identical(results: Path) -> None:
    evaluate(results, FakeLLM(finish_script(4), model="offline-agent"))
    metrics = read_json(stage_dir("f2") / "metrics.json")
    metrics["additional_audit_note"] = "different snapshot"
    write_json(stage_dir("f2") / "metrics.json", metrics)
    llm = FakeLLM([], model="offline-agent")
    with pytest.raises(ValueError, match=r"context|selection"):
        evaluate(results, llm)
    assert not llm.calls


def test_explicit_arm_allows_an_honest_partial_arm_experiment(results: Path) -> None:
    publish({"text_trace": 0.0})
    _, choice = select("text_trace")
    assert choice.reason == "explicit_override" and choice.arm == "text_trace"
    with pytest.raises(ValueError, match="missing arm"):
        select()


def test_custom_optimisation_directory(results: Path) -> None:
    custom = results / "custom-f2"
    custom.mkdir()
    for name in ("run.json", "metrics.json"):
        write_json(custom / name, read_json(stage_dir("f2") / name))
    _, choice = select_optimised(
        "shop", model="offline-agent", execution="test_double", optimisation_dir=custom
    )
    assert choice.optimisation_dir == str(custom)
