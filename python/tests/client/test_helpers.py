"""Check shared path, serialization, pricing, and reproducibility helpers."""

import random

import numpy as np
import pytest

from specx.client import io, paths
from specx.client.pricing import cost_usd
from specx.client.seeding import seed_everything


def test_results_paths_are_rooted_and_create_parents(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path / "runs"))
    assert paths.tools_path("shop").name == "shop.tools.json"
    assert (
        paths.tools_path("shop", "optimised.text_trace").name
        == "shop.optimised.text_trace.tools.json"
    )
    assert paths.contracts_path("admin").name == "admin.contracts.json"
    assert paths.verdicts_path("s1").name == "s1.jsonl"
    assert paths.trials_path("generated").name == "generated.jsonl"
    for path in (
        paths.graphs_dir(),
        paths.traces_dir(),
        paths.patches_dir(),
        paths.stage_dir("s6"),
    ):
        assert path.is_dir()
        assert path.is_relative_to(tmp_path / "runs")
    assert paths.tools_path("shop").parent.is_dir()


def test_relative_results_paths_do_not_depend_on_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPECX_RESULTS_DIR", "results")
    assert paths.results_dir() == paths.repo_root() / "results"


@pytest.mark.parametrize("name", ["../outside", "/absolute", "", "a/b", ".."])
def test_paths_reject_traversal(monkeypatch, tmp_path, name):
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        paths.tools_path(name)


def test_json_and_jsonl_roundtrip(tmp_path):
    record = {"z": [1, "café"], "a": True}
    path = tmp_path / "nested/data.json"
    io.write_json(path, record)
    assert io.read_json(path) == record
    assert path.read_text().startswith('{\n  "a":')
    lines = tmp_path / "nested/data.jsonl"
    io.write_jsonl(lines, [record])
    io.append_jsonl(lines, {"next": 2})
    assert io.read_jsonl(lines) == [record, {"next": 2}]
    io.write_jsonl(lines, [])
    assert io.read_jsonl(lines) == []


def test_seeding_repeats_python_and_numpy():
    seed_everything(12)
    before = (random.random(), np.random.random())
    seed_everything(12)
    assert (random.random(), np.random.random()) == before


def test_documented_pricing_and_unknown_models():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == 12
    assert cost_usd("claude-opus-5-5", 1_000_000, 1_000_000) == 24
    with pytest.raises(ValueError, match="Unknown model"):
        cost_usd("unpriced-model", 10, 10)
    with pytest.raises(ValueError):
        cost_usd("claude-sonnet-5-5", -1, 10)


def test_malformed_jsonl_reports_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\n\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:3:"):
        io.read_jsonl(path)


def test_seed_everything_seeds_optional_torch(monkeypatch):
    import sys
    from unittest.mock import Mock

    torch = Mock()
    torch.cuda.is_available.return_value = True
    monkeypatch.setitem(sys.modules, "torch", torch)
    seed_everything(19)
    torch.manual_seed.assert_called_once_with(19)
    torch.cuda.manual_seed_all.assert_called_once_with(19)
