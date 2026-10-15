"""Select F2 arms using training metrics only and replay accepted metadata patches.

Fail closed on incomplete experiments or inconsistent published artefacts. No
held-out outcomes are read here, and no optimised tool files are rewritten.
"""

import hashlib
import math
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from specx.client.io import read_json
from specx.client.paths import patches_dir, repo_root, stage_dir, tools_path
from specx.client.schemas import validate
from specx.evalx.conditions import Condition, select_tools, tool_set_for, tool_set_version
from specx.evalx.tasks import load_tasks
from specx.optim.gate import GateDecision
from specx.optim.patch import apply_patch
from specx.optim.reviser import Arm

Rate = Annotated[float, Field(ge=0, le=1)]


class OptimisationSelection(BaseModel):
    app: str
    arm: Arm
    reason: Literal["best_train_success", "explicit_override"]
    train_success_by_arm: dict[str, float]
    accepted_patches: int
    no_accepted_patches: bool
    identical_to_verified: bool
    verified_tool_set_version: str
    optimised_tool_set_version: str
    metrics_sha256: str
    optimisation_run_sha256: str
    accepted_patch_sha256: dict[str, str]
    optimisation_dir: str
    note: str


class _ArmMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    success_by_iter: list[Rate] = Field(min_length=1)
    proposed: int = Field(ge=0)
    accepted: int = Field(ge=0)
    revisions: list[dict[str, Any]]


class _TrainingArgs(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    apps: list[Literal["shop", "admin"]] = Field(min_length=1)
    arms: list[str] = Field(min_length=1)
    trials: int = Field(ge=1)
    seed: int = Field(ge=0)
    task_ids: list[str] | None = None
    split: Literal["train"] = "train"


class _Run(BaseModel):
    status: Literal["complete"]
    models: dict[str, str]
    execution: Literal["real", "test_double"]
    args: _TrainingArgs


def verified_tools(app: str) -> list[dict[str, Any]]:
    tools, _ = tool_set_for(app, Condition.verified)
    if not tools or any(tool["metadata_revision"] != 0 for tool in tools):
        raise ValueError("Evaluation requires a nonempty verified revision-zero tool set")
    return tools


def _check_candidate(
    app: str,
    arm: Arm,
    row: _ArmMetrics,
    initial: list[dict[str, Any]],
    reviser_model: str,
    patch_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    if row.proposed != len(row.revisions) or row.accepted != sum(
        log.get("accepted") is True for log in row.revisions
    ):
        raise ValueError("F2 proposal/acceptance counts disagree with revision history")
    if any(
        right < left
        for left, right in zip(row.success_by_iter, row.success_by_iter[1:], strict=False)
    ):
        raise ValueError("F2 accepted success history cannot decrease")
    if row.accepted == 0 and len(set(row.success_by_iter)) != 1:
        raise ValueError("No accepted patches but F2 training success changed")
    reconstructed = {tool["tool_id"]: tool for tool in initial}
    current_success = row.success_by_iter[0]
    for log in row.revisions:
        decision = GateDecision.model_validate(log)
        if decision.accepted != (decision.reason == "improved"):
            raise ValueError("F2 gate decision has inconsistent acceptance and reason")
        if log.get("app") != app or log.get("arm") != arm.value:
            raise ValueError("Wrong app/arm in F2 revision history")
        if log.get("accepted") is not True:
            continue
        identity, iteration = log.get("tool_id"), log.get("iter")
        if (
            not isinstance(identity, str)
            or identity not in reconstructed
            or type(iteration) is not int
            or iteration < 1
        ):
            raise ValueError("Invalid F2 revision target/iteration")
        if log.get("reason") != "improved":
            raise ValueError("Accepted F2 revision must have reason improved")
        if (
            decision.success is None
            or decision.success.n < 10
            or decision.success.diff <= 0
            or decision.success.p > 0.1
            or decision.safety.get("passed") is not True
        ):
            raise ValueError("Accepted F2 revision does not meet the statistical/safety gate")
        if not math.isclose(decision.success.a_mean, current_success, abs_tol=1e-12):
            raise ValueError("F2 accepted gates do not form a continuous training-success history")
        current_success = decision.success.b_mean
        patch_path = patches_dir() / f"{app}.{arm.value}.{iteration}.{identity}.patch.json"
        patch = read_json(patch_path)
        validate("patch", patch)
        patch_hashes[patch_path.name] = hashlib.sha256(patch_path.read_bytes()).hexdigest()
        if (
            patch.get("patch_id") != log.get("patch_id")
            or patch.get("modality") != arm.value
            or patch.get("model") != reviser_model
        ):
            raise ValueError("Accepted patch provenance disagrees with F2 run")
        reconstructed[identity] = apply_patch(reconstructed[identity], patch)
    if not math.isclose(current_success, row.success_by_iter[-1], abs_tol=1e-12):
        raise ValueError("Final F2 train success disagrees with accepted gate history")
    records = read_json(tools_path(app, f"optimised.{arm.value}"))
    if not isinstance(records, list):
        raise ValueError("Expected optimised tool array")
    tools = select_tools(app, records, Condition.optimised)
    if len(tools) != len(records) or {tool["tool_id"]: tool for tool in tools} != reconstructed:
        raise ValueError("Optimised tools do not match verified tools plus accepted patch history")
    return tools


def select_optimised(
    app: str,
    *,
    model: str,
    execution: str,
    arm: str | None = None,
    optimisation_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], OptimisationSelection]:
    directory = optimisation_dir or stage_dir("f2")
    if not directory.is_absolute():
        directory = repo_root() / directory
    run_path, metrics_path = directory / "run.json", directory / "metrics.json"
    run = _Run.model_validate(read_json(run_path))
    metrics = read_json(metrics_path)
    if run.models.get("agent") != model or not run.models.get("reviser"):
        raise ValueError("F2 and evaluation must use the same frozen agent model")
    if (
        not isinstance(metrics, dict)
        or run.execution != execution
        or metrics.get("execution") != execution
    ):
        raise ValueError("Cannot mix live and test-double optimisation/evaluation evidence")
    if app not in run.args.apps:
        raise ValueError("F2 run does not contain this app's training experiment")
    known_train = {
        task.task_id for name in run.args.apps for task in load_tasks(name) if task.split == "train"
    }
    requested = run.args.task_ids
    if requested is not None and (not requested or not set(requested) <= known_train):
        raise ValueError("F2 run includes unknown or heldout task IDs")
    initial = verified_tools(app)
    arms = [Arm(arm)] if arm is not None else list(Arm)
    rows, candidates = {}, {}
    patch_hashes: dict[str, str] = {}
    for candidate_arm in arms:
        if candidate_arm.value not in run.args.arms:
            raise ValueError(f"Incomplete F2 experiment: missing arm {candidate_arm.value}")
        record = metrics.get("apps", {}).get(app, {}).get(candidate_arm.value)
        if record is None:
            raise ValueError(f"Missing F2 training metrics for {app}/{candidate_arm.value}")
        row = _ArmMetrics.model_validate(record)
        rows[candidate_arm] = row
        candidates[candidate_arm] = _check_candidate(
            app, candidate_arm, row, initial, run.models["reviser"], patch_hashes
        )
    if len({row.success_by_iter[0] for row in rows.values()}) != 1:
        raise ValueError("F2 arms must share the same training baseline")
    preference = {Arm.text_trace: 0, Arm.text_structured: 1, Arm.multimodal_structured: 2}
    chosen = max(arms, key=lambda item: (rows[item].success_by_iter[-1], preference[item]))
    tools, row = candidates[chosen], rows[chosen]
    equal = {tool["tool_id"]: tool for tool in tools} == {tool["tool_id"]: tool for tool in initial}
    note = (
        f"{app}: no accepted patches in selected arm {chosen.value}; optimised == verified. "
        "Separate stochastic evaluation outcomes may still differ."
        if row.accepted == 0
        else f"{app}: selected {chosen.value} with {row.accepted} accepted patches."
    )
    return tools, OptimisationSelection(
        app=app,
        arm=chosen,
        reason="explicit_override" if arm is not None else "best_train_success",
        train_success_by_arm={item.value: rows[item].success_by_iter[-1] for item in arms},
        accepted_patches=row.accepted,
        no_accepted_patches=row.accepted == 0,
        identical_to_verified=equal,
        verified_tool_set_version=tool_set_version(app, initial, Condition.verified),
        optimised_tool_set_version=tool_set_version(app, tools, Condition.optimised),
        metrics_sha256=hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        optimisation_run_sha256=hashlib.sha256(run_path.read_bytes()).hexdigest(),
        accepted_patch_sha256=patch_hashes,
        optimisation_dir=str(directory.resolve()),
        note=note,
    )
