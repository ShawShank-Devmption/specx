"""C10 reports use actual published artefacts; synthetic inputs stay in temp paths."""

from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specx.client.io import read_json, read_jsonl, write_json, write_jsonl
from specx.client.paths import repo_root
from specx.stats.report import app, write_report


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    root = tmp_path / "results"
    fixtures = repo_root() / "fixtures"
    tools = read_json(fixtures / "tools/shop.tools.json")
    tools[2]["status"] = "quarantined"
    write_json(root / "tools/shop.tools.json", tools)
    write_jsonl(
        root / "verdicts/f1.jsonl",
        read_jsonl(fixtures / "verdicts/sample.verdicts.jsonl"),
    )
    trial_rows = read_jsonl(next((fixtures / "trials").glob("*.jsonl")))
    for condition in ("raw_dom", "generated", "verified", "optimised"):
        template = next(row for row in trial_rows if row["condition"] == condition)
        rows = []
        for task in ("t01", "t07", "t08", "t09", "t10"):
            row = deepcopy(template)
            row.update(trial_id=f"shop.{task}.{condition}.s0", task_id=f"shop.{task}")
            rows.append(row)
        write_jsonl(root / f"trials/{condition}.jsonl", rows)
    write_json(
        root / "s6/metrics.json",
        {
            "n_train": 20,
            "thresholds": {"iforest": 0.6, "lstm": 0.1},
            "per_kind": {
                kind: {"n": 10, "det_if": 0.8, "det_lstm": 0.7, "det_both": 0.9}
                for kind in (
                    "delayed_post",
                    "storage_write",
                    "third_party_fetch",
                    "background_poll",
                )
            },
            "benign": {"n": 10, "fpr_if": 0.1, "fpr_lstm": 0.1, "fpr_both": 0.1},
            "contract_only_detection": {
                kind: 0.5
                for kind in (
                    "delayed_post",
                    "storage_write",
                    "third_party_fetch",
                    "background_poll",
                )
            },
        },
    )
    write_json(
        root / "s1/metrics.json",
        {
            "shop": {
                method: {
                    "n": 3,
                    "unique_signatures_per_1000": {"mean": 2.5, "sd": 0.1},
                    "ttf_high": 3,
                }
                for method in ("random", "coverage", "ppo")
            }
        },
    )
    write_json(
        root / "s2/metrics.json",
        {
            "n_train": 10,
            "n_test": 5,
            "link": {
                "rule": {"p": 0.5, "r": 0.5},
                "gcn": {"auc": 0.8, "p": 0.7, "r": 0.6, "f1": 0.65},
            },
            "path": {
                method: {"auc": 0.8, "p": 0.7, "r": 0.6, "f1": 0.65} for method in ("mlp", "gcn")
            },
            "recovered_edges": [],
        },
    )
    f2 = {
        "execution": "test_double",
        "apps": {
            "shop": {
                arm: {
                    "success_by_iter": [0.4],
                    "iterations_to_convergence": 0,
                    "proposed": 0,
                    "accepted": 0,
                    "rejected": {},
                    "revisions": [],
                }
                for arm in ("text_trace", "text_structured", "multimodal_structured")
            }
        },
    }
    write_json(root / "f2/metrics.json", f2)
    write_json(
        root / "f2/run.json",
        {
            "status": "complete",
            "models": {"agent": template["agent_model"], "reviser": "offline-reviser"},
            "execution": "test_double",
            "args": {"trials": 1, "task_ids": ["shop.t02"]},
        },
    )
    write_json(
        root / "evalx/run.json",
        {
            "status": "complete",
            "execution": "test_double",
            "models": {"agent": template["agent_model"]},
            "optimisation_selection": {
                "shop": {
                    "arm": "multimodal_structured",
                    "no_accepted_patches": True,
                    "note": "shop: optimised == verified (no accepted patches).",
                }
            },
        },
    )
    return root


def test_complete_report_and_dashboard_copy(inputs: Path, tmp_path: Path) -> None:
    numbers, status = write_report(
        inputs, tmp_path / "final", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
    )
    assert status == 0 and numbers["complete"]
    assert numbers["execution"] == "test_double"
    assert numbers["t1_generation"][0]["tools_generated"] == 3
    assert len(numbers["t7_readiness"]["comparisons"]) == 9
    assert all(
        row["n"] == 5 and row["p_holm"] is not None
        for row in numbers["t7_readiness"]["comparisons"]
    )
    assert numbers["n"]["raw_dom"]["shop"] == 5
    assert numbers["quarantine"][0]["tool_id"] == "shop.place_order"
    report = (tmp_path / "final/REPORT.md").read_text()
    assert "Table 7" in report and "Deviations from plan" in report
    assert "optimised == verified" in report and "test_double" in report
    assert read_json(tmp_path / "public/numbers.json") == numbers


def test_missing_inputs_emit_report_and_exit_two(tmp_path: Path) -> None:
    numbers, status = write_report(
        tmp_path / "missing", tmp_path / "out", dashboard_public=tmp_path / "public"
    )
    assert status == 2 and not numbers["complete"]
    report = (tmp_path / "out/REPORT.md").read_text()
    assert report.count("MISSING:") >= 7
    assert "s6/metrics.json" in report
    assert numbers["t7_readiness"]["conditions"]["raw_dom"]["shop"]["success_rate"] is None


def test_invalid_boundary_record_fails_before_output(inputs: Path, tmp_path: Path) -> None:
    write_json(inputs / "tools/shop.tools.json", [{"tool_id": "broken"}])
    with pytest.raises(ValueError):
        write_report(inputs, tmp_path / "out", dashboard_public=tmp_path / "public")
    assert not (tmp_path / "out/numbers.json").exists()


def test_training_and_gate_trials_cannot_enter_readiness(inputs: Path, tmp_path: Path) -> None:
    rows = read_jsonl(inputs / "trials/raw_dom.jsonl")
    extra = deepcopy(rows[0])
    extra.update(task_id="shop.t02", trial_id="shop.t02.raw_dom.s0", split="train", success=True)
    write_jsonl(inputs / "trials/raw_dom.jsonl", [*rows, extra])
    write_jsonl(inputs / "trials/gate_shop_baseline.jsonl", [extra])
    numbers, _ = write_report(
        inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
    )
    assert numbers["n"]["raw_dom"]["shop"] == 5
    assert numbers["t7_readiness"]["conditions"]["raw_dom"]["shop"]["success_rate"] == 0


def test_missing_pairs_report_actual_n_and_missing_cohort(inputs: Path, tmp_path: Path) -> None:
    rows = read_jsonl(inputs / "trials/generated.jsonl")
    write_jsonl(inputs / "trials/generated.jsonl", rows[:-1])
    numbers, status = write_report(
        inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
    )
    assert status == 2
    comparisons = numbers["t7_readiness"]["comparisons"]
    assert next(row["n"] for row in comparisons if row["from_condition"] == "raw_dom") == 4


def test_mixed_models_and_duplicate_pairs_are_rejected(inputs: Path, tmp_path: Path) -> None:
    path = inputs / "trials/raw_dom.jsonl"
    rows = read_jsonl(path)
    rows[0]["agent_model"] = "different-model"
    write_jsonl(path, rows)
    with pytest.raises(ValueError, match="model"):
        write_report(
            inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
        )
    rows[0]["agent_model"] = rows[1]["agent_model"]
    write_jsonl(path, [*rows, rows[0]])
    with pytest.raises(ValueError, match="Duplicate"):
        write_report(
            inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
        )


def test_cli_missing_inputs_is_two(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "--results",
            str(tmp_path / "absent"),
            "--out",
            str(tmp_path / "final"),
            "--dashboard-public",
            str(tmp_path / "public"),
        ],
    )
    assert result.exit_code == 2


@pytest.mark.parametrize("stage", ["s6", "s2"])
def test_invalid_safety_rate_is_not_published(inputs: Path, tmp_path: Path, stage: str) -> None:
    path = inputs / stage / "metrics.json"
    data = read_json(path)
    if stage == "s6":
        data["benign"]["fpr_if"] = 1.5
    else:
        data["link"]["gcn"]["auc"] = -0.1
    write_json(path, data)
    with pytest.raises(ValueError, match="rate"):
        write_report(
            inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
        )
    assert not (tmp_path / "out/numbers.json").exists()


def test_empty_safety_samples_and_missing_arm_are_incomplete(inputs: Path, tmp_path: Path) -> None:
    safety = read_json(inputs / "s6/metrics.json")
    safety["benign"]["n"] = 0
    write_json(inputs / "s6/metrics.json", safety)
    f2 = read_json(inputs / "f2/metrics.json")
    del f2["apps"]["shop"]["multimodal_structured"]
    write_json(inputs / "f2/metrics.json", f2)
    numbers, status = write_report(
        inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
    )
    assert status == 2 and any("n=0" in item for item in numbers["missing"])
    assert any("multimodal_structured" in item for item in numbers["missing"])


def test_metadata_model_contradiction_is_rejected(inputs: Path, tmp_path: Path) -> None:
    run = read_json(inputs / "f2/run.json")
    run["models"]["agent"] = "different-agent"
    write_json(inputs / "f2/run.json", run)
    with pytest.raises(ValueError, match="model"):
        write_report(
            inputs, tmp_path / "out", apps=["shop"], trials=1, dashboard_public=tmp_path / "public"
        )
