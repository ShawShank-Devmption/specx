from copy import deepcopy

import pytest

from specx.client.io import read_json
from specx.client.paths import repo_root
from specx.optim.patch import StalePatch, apply_patch


def tool_and_patch(op: dict) -> tuple[dict, dict]:
    tool = read_json(repo_root() / "fixtures/tools/shop.tools.json")[1]
    patch = {
        "patch_id": "p",
        "tool_id": tool["tool_id"],
        "base_metadata_revision": 0,
        "source_trial_ids": ["t"],
        "modality": "text_trace",
        "model": "offline",
        "ops": [{"rationale": "test", **op}],
    }
    return tool, patch


@pytest.mark.parametrize(
    "op,path,value",
    [
        ({"op": "rename", "value": "add_product"}, ["name"], "add_product"),
        ({"op": "set_description", "value": "new description"}, ["description"], "new description"),
        (
            {"op": "set_param_description", "param": "qty", "value": "Units"},
            ["input_schema", "properties", "qty", "description"],
            "Units",
        ),
        (
            {"op": "add_enum", "param": "qty", "value": [1, 2, 2]},
            ["input_schema", "properties", "qty", "enum"],
            [1, 2],
        ),
        (
            {"op": "set_example", "param": "qty", "value": 3},
            ["input_schema", "properties", "qty", "examples"],
            [3],
        ),
        (
            {"op": "mark_required", "param": "qty"},
            ["input_schema", "required"],
            ["product_id", "qty"],
        ),
    ],
)
def test_ops_are_pure(op: dict, path: list[str], value: object) -> None:
    tool, patch = tool_and_patch(op)
    original = deepcopy(tool)
    result = apply_patch(tool, patch)
    actual = result
    for key in path:
        actual = actual[key]
    assert actual == value
    assert tool == original and result["metadata_revision"] == 1
    for key in (
        "handler",
        "risk_level",
        "atomic",
        "provenance",
        "version",
        "status",
        "output_schema",
    ):
        assert result[key] == tool[key]


def test_selector_replaces_code_and_inventory_only() -> None:
    tool, patch = tool_and_patch({"op": "fix_selector", "old_value": "#old", "value": "#new"})
    tool["handler"] = {
        "kind": "ui",
        "code": "async () => document.querySelector('#old').click()",
        "selectors": ["#old", "#other"],
    }
    result = apply_patch(tool, patch)
    assert result["handler"]["selectors"] == ["#new", "#other"]
    assert "#new" in result["handler"]["code"] and "#old" in tool["handler"]["code"]


def test_apply_refuses_stale_revision() -> None:
    tool, patch = tool_and_patch({"op": "set_description", "value": "new"})
    patch["base_metadata_revision"] = 1
    with pytest.raises(StalePatch):
        apply_patch(tool, patch)


@pytest.mark.parametrize(
    "op",
    [
        {"op": "set_param_description", "param": "absent", "value": "new"},
        {"op": "set_description", "value": 3},
        {"op": "add_enum", "param": "qty", "value": "bad"},
        {"op": "fix_selector", "old_value": "missing", "value": "other"},
        {"op": "set_example", "param": "qty"},
    ],
)
def test_rejects_invalid_semantics(op: dict) -> None:
    tool, patch = tool_and_patch(op)
    with pytest.raises(ValueError):
        apply_patch(tool, patch)


def test_enum_union_and_required_append() -> None:
    tool, patch = tool_and_patch({"op": "add_enum", "param": "qty", "value": [2, 3]})
    tool["input_schema"]["properties"]["qty"]["enum"] = [1, 2]
    tool["input_schema"]["required"] = ["product_id"]
    patch["ops"].append({"op": "mark_required", "param": "qty", "rationale": "test"})
    result = apply_patch(tool, patch)
    assert result["input_schema"]["properties"]["qty"]["enum"] == [1, 2, 3]
    assert result["input_schema"]["required"] == ["product_id", "qty"]
