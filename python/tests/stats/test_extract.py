"""Verify evidence counting and replay comparisons against published records."""

from copy import deepcopy
from pathlib import Path

import pytest

from specx.client.io import read_json, read_jsonl, write_json, write_jsonl
from specx.client.paths import repo_root
from specx.stats.extract import generation_table, verification_table


def test_generation_counts_unique_surfaces_not_provenance_entries(tmp_path: Path) -> None:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[0]["provenance"].append(deepcopy(tools[0]["provenance"][0]))
    path = tmp_path / "shop.tools.json"
    write_json(path, tools)
    row = generation_table([path])[0]
    assert row["tools_generated"] == 3
    assert row["mean_provenance_surfaces"] == 3
    assert row["tools_ge3_surfaces"] == 2


def test_quarantine_reasons_and_replay_require_actual_matching_evidence(tmp_path: Path) -> None:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[2]["status"] = "quarantined"
    tools_path = tmp_path / "shop.tools.json"
    write_json(tools_path, tools)
    verdicts = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")
    replay = {
        **deepcopy(verdicts[0]),
        "run_id": "replay1",
        "mode": "replay",
        "started_at": "2026-10-15T09:00:10Z",
    }
    unmatched = {**deepcopy(replay), "run_id": "unmatched", "session_id": "other"}
    changed = {**deepcopy(replay), "run_id": "changed", "started_at": "2026-10-15T09:00:20Z"}
    changed["effect_diff"]["db"]["cart_items"]["inserted"] = 2
    path = tmp_path / "verdicts.jsonl"
    write_jsonl(path, [*verdicts, replay, unmatched, changed])
    row = verification_table([tools_path], [path])[0]
    assert row["verified"] == 2 and row["quarantined"] == 1 and row["unverifiable"] == 0
    assert row["quarantine_reasons"] == {"race": 1}
    assert row["replay_determinism_rate"] == 0.5
    assert row["replay_n"] == 2 and row["replay_unmatched"] == 1


def test_missing_replay_evidence_is_not_assumed_deterministic() -> None:
    row = verification_table(
        [repo_root() / "fixtures/tools/shop.tools.json"],
        [repo_root() / "fixtures/verdicts/sample.verdicts.jsonl"],
    )[0]
    assert row["replay_determinism_rate"] is None and row["replay_n"] == 0
    assert row["generated"] == 1


def test_unverifiable_is_derived_from_verdict_without_new_tool_status(tmp_path: Path) -> None:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    verdict = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[0]
    verdict["tool_id"] = tools[2]["tool_id"]
    verdict["status"] = "unverifiable"
    path, verdict_path = tmp_path / "shop.tools.json", tmp_path / "v.jsonl"
    write_json(path, tools)
    write_jsonl(verdict_path, [verdict])
    assert verification_table([path], [verdict_path])[0]["unverifiable"] == 1


def test_extraction_rejects_duplicate_tool_ids() -> None:
    path = repo_root() / "fixtures/tools/shop.tools.json"
    with pytest.raises(ValueError, match="Duplicate"):
        generation_table([path, path])


def test_failing_clause_changes_replay_determinism_even_when_db_matches(tmp_path: Path) -> None:
    original = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[0]
    replay = {
        **deepcopy(original),
        "run_id": "replay",
        "mode": "replay",
        "started_at": "2026-10-15T09:00:10Z",
    }
    replay["clause_results"][0]["passed"] = False
    path = tmp_path / "v.jsonl"
    write_jsonl(path, [original, replay])
    row = verification_table([repo_root() / "fixtures/tools/shop.tools.json"], [path])[0]
    assert row["replay_determinism_rate"] == 0 and row["replay_n"] == 1


def test_nonverification_replays_do_not_pollute_table_two(tmp_path: Path) -> None:
    verdict = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[0]
    verdict.update({"mode": "replay", "source": "s1"})
    path = tmp_path / "s1.jsonl"
    write_jsonl(path, [verdict])
    row = verification_table([repo_root() / "fixtures/tools/shop.tools.json"], [path])[0]
    assert row["replay_total"] == 0
