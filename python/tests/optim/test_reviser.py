"""C8 request-shape, trust-boundary and image/dataset regression tests."""

import base64
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from specx.client.io import read_json, read_jsonl
from specx.client.paths import repo_root
from specx.evalx.llm import AnthropicLLM, FakeLLM
from specx.optim.bundles import FailureBundle, synthetic_failures
from specx.optim.dataset import export_accepted
from specx.optim.reviser import Arm, propose

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


def evidence(n: int = 1) -> tuple[dict, list[FailureBundle]]:
    tool = read_json(repo_root() / "fixtures/tools/shop.tools.json")[1]
    bundles = synthetic_failures([tool], n, seed=0)
    for bundle in bundles:
        bundle.synthetic = False
        bundle.synthetic_mutation = None
        bundle.screenshot_b64 = PNG
    return tool, bundles


def answer(payload: object) -> dict:
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "usage": {},
    }


def ops() -> dict:
    return {
        "ops": [
            {
                "op": "set_description",
                "value": "Use the correct product id from the catalogue.",
                "rationale": "Clarify selection",
            }
        ]
    }


@pytest.mark.parametrize("arm", [Arm.text_structured, Arm.multimodal_structured])
def test_structured_request_and_local_envelope(arm: Arm) -> None:
    tool, bundles = evidence(5)
    original = deepcopy(bundles)
    llm = FakeLLM([answer(ops())], model="offline-reviser")
    patch = propose(arm, bundles, tool, llm=llm)
    assert patch["tool_id"] == tool["tool_id"] and patch["base_metadata_revision"] == 0
    assert patch["model"] == llm.model and patch["modality"] == arm
    assert patch["source_trial_ids"] == [bundle.trial_id for bundle in bundles]
    call = llm.calls[0]
    assert len(llm.calls) == 1 and call["max_tokens"] == 4096
    assert call["output_config"]["effort"] == "high"
    schema = call["output_config"]["format"]["schema"]
    assert schema["required"] == ["ops"]
    assert "tool_id" not in schema["properties"] and "maxItems" not in schema["properties"]["ops"]
    content = call["messages"][0]["content"]
    images = [block for block in content if block["type"] == "image"]
    assert len(images) == (3 if arm == Arm.multimodal_structured else 0)
    if images:
        assert content[:3] == images and images[0]["source"]["data"] == PNG
    assert PNG not in content[-1]["text"]
    assert "CURRENT TOOL" in content[-1]["text"] and "DOM DIFF" in content[-1]["text"]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert bundles == original


@pytest.mark.parametrize(
    "payload",
    [
        {**ops(), "tool_id": "forged"},
        {"ops": []},
        {"ops": [{"op": "set_description", "value": 42, "rationale": "bad"}]},
        {
            "ops": [
                {
                    "op": "set_param_description",
                    "param": "missing",
                    "value": "description",
                    "rationale": "bad",
                }
            ]
        },
        {
            "ops": [
                {
                    "op": "set_description",
                    "value": "long enough description",
                    "rationale": "bad",
                    "handler": "forged",
                }
            ]
        },
        {**ops(), "confidence": 1.1},
    ],
)
def test_invalid_structured_patch_is_rejected(payload: dict) -> None:
    tool, bundles = evidence()
    with pytest.raises(ValueError):
        propose(Arm.text_structured, bundles, tool, llm=FakeLLM([answer(payload)], model="offline"))


@pytest.mark.parametrize("stop", ["refusal", "max_tokens", "tool_use"])
def test_structured_incomplete_response_rejected(stop: str) -> None:
    tool, bundles = evidence()
    response = answer(ops())
    response["stop_reason"] = stop
    with pytest.raises(ValueError, match="completed"):
        propose(Arm.text_structured, bundles, tool, llm=FakeLLM([response], model="offline"))


def test_malformed_json_rejected_without_second_call() -> None:
    tool, bundles = evidence()
    response = answer(ops())
    response["content"][0]["text"] = "not JSON"
    llm = FakeLLM([response], model="offline")
    with pytest.raises(ValueError):
        propose(Arm.text_structured, bundles, tool, llm=llm)
    assert len(llm.calls) == 1


def test_missing_screenshot_is_explicit_not_fabricated() -> None:
    tool, bundles = evidence()
    bundles[0].screenshot_b64 = None
    llm = FakeLLM([answer(ops())], model="offline")
    propose(Arm.multimodal_structured, bundles, tool, llm=llm)
    content = llm.calls[0]["messages"][0]["content"]
    assert all(block["type"] != "image" for block in content)
    assert "unavailable" in content[0]["text"].lower()


def test_export_writes_png_without_inline_screenshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    tool, bundles = evidence()
    patch = propose(
        Arm.multimodal_structured, bundles, tool, llm=FakeLLM([answer(ops())], model="offline")
    )
    export_accepted(bundles, patch, Arm.multimodal_structured.value)
    row = read_jsonl(tmp_path / "s4/dataset.jsonl")[0]
    assert set(row) == {"bundle_without_screenshot", "screenshot_path", "accepted_patch", "arm"}
    assert PNG not in json.dumps(row) and "screenshot_b64" not in row["bundle_without_screenshot"]
    assert (tmp_path / "s4" / row["screenshot_path"]).read_bytes() == base64.b64decode(PNG)
    assert bundles[0].screenshot_b64 == PNG
    bundles[0].screenshot_b64 = None
    export_accepted(bundles, patch, Arm.multimodal_structured.value)
    assert read_jsonl(tmp_path / "s4/dataset.jsonl")[1]["screenshot_path"] is None


@pytest.mark.parametrize("image", ["bad!base64", base64.b64encode(b"not a PNG").decode()])
def test_invalid_image_rejected_before_model_call(image: str) -> None:
    tool, bundles = evidence()
    bundles[0].screenshot_b64 = image
    llm = FakeLLM([answer(ops())], model="offline")
    with pytest.raises(ValueError, match="PNG"):
        propose(Arm.multimodal_structured, bundles, tool, llm=llm)
    assert not llm.calls


@pytest.mark.parametrize("arm", list(Arm))
def test_every_arm_rejects_heldout_before_model_call(arm: Arm) -> None:
    tool, bundles = evidence()
    bundles[0].split = "heldout"
    llm = FakeLLM([answer(ops())], model="offline")
    with pytest.raises(ValueError, match="train-only"):
        propose(arm, bundles, tool, llm=llm)
    assert not llm.calls


@pytest.mark.parametrize("arm", [Arm.text_trace, Arm.text_structured])
def test_text_arms_remove_nested_images(arm: Arm) -> None:
    tool, bundles = evidence()
    bundles[0].transcript_tail = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": PNG},
                },
            ],
        }
    ]
    response = (
        answer(ops())
        if arm == Arm.text_structured
        else {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Replacement description."}],
            "usage": {},
        }
    )
    llm = FakeLLM([response], model="offline")
    propose(arm, bundles, tool, llm=llm)
    assert PNG not in json.dumps(llm.calls)


def test_dataset_rejects_heldout_and_keeps_contract_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    tool, bundles = evidence()
    path = repo_root() / "contracts/patch.schema.json"
    original = path.read_bytes()
    patch = propose(
        Arm.text_structured, bundles, tool, llm=FakeLLM([answer(ops())], model="offline")
    )
    assert path.read_bytes() == original
    bundles[0].split = "heldout"
    with pytest.raises(ValueError, match="train-only"):
        export_accepted(bundles, patch, Arm.text_structured.value)
    assert not (tmp_path / "s4/dataset.jsonl").exists()


@pytest.mark.llm
def test_live_structured_reviser_smoke() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("SPECX_GEN_MODEL"):
        pytest.skip("Live smoke requires ANTHROPIC_API_KEY and SPECX_GEN_MODEL")
    tool, bundles = evidence()
    llm = AnthropicLLM(model=os.environ["SPECX_GEN_MODEL"])
    try:
        patch = propose(Arm.text_structured, bundles, tool, llm=llm)
        assert patch["ops"] and patch["modality"] == "text_structured"
    finally:
        llm.close()
