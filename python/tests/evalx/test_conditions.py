"""Check that only the intended tools are shipped under each condition."""

from pathlib import Path

import pytest

from specx.client.io import read_json, write_json
from specx.client.paths import repo_root, tools_path
from specx.evalx.conditions import Condition, tool_set_for, tool_set_version


def test_raw_dom_has_no_tool_file_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path / "absent"))
    assert tool_set_for("shop", Condition.raw_dom) == ([], "none")
    assert not (tmp_path / "absent").exists()


def test_condition_filters_and_optimised_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[2]["status"] = "quarantined"
    write_json(tools_path("shop"), tools)
    assert len(tool_set_for("shop", Condition.generated)[0]) == 3
    assert len(tool_set_for("shop", Condition.verified)[0]) == 2
    tools[1]["metadata_revision"] = 1
    write_json(tools_path("shop", "optimised.text_structured"), tools)
    optimised, version = tool_set_for("shop", Condition.optimised, "text_structured")
    assert len(optimised) == 2 and version.startswith("shop@v1.r1")
    assert tool_set_version("shop", list(reversed(optimised)), Condition.optimised) == version
    tools[0]["metadata_revision"] = 1
    write_json(tools_path("shop", "optimised.text_structured"), tools)
    assert tool_set_for("shop", Condition.optimised, "text_structured")[1] != version


def test_optimised_requires_explicit_arm() -> None:
    with pytest.raises(ValueError, match="arm"):
        tool_set_for("shop", Condition.optimised)
