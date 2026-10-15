"""Exercise the shared validator against the integration fixtures and invalid records."""

import json

import pytest

from specx.client.paths import repo_root
from specx.client.schemas import validate


def test_every_fixture_validates():
    kinds = {
        "apps": "app_manifest",
        "tools": "tool_definition",
        "contracts": "contract",
        "events": "event_record",
        "graphs": "workflow_graph",
        "patches": "patch",
        "tasks": "task",
        "trials": "trial_result",
        "verdicts": "verdict",
    }
    for folder, schema in kinds.items():
        for path in (repo_root() / "fixtures" / folder).iterdir():
            if path.suffix == ".jsonl":
                records = [
                    json.loads(line) for line in path.read_text().splitlines() if line.strip()
                ]
            else:
                data = json.loads(path.read_text())
                records = data if isinstance(data, list) else [data]
            for record in records:
                validate(schema, record)


def test_invalid_record_reports_pointer():
    tool = json.loads((repo_root() / "fixtures/tools/shop.tools.json").read_text())[0]
    tool["name"] = "INVALID"
    with pytest.raises(ValueError, match="tool_definition/name:"):
        validate("tool_definition", tool)


def test_format_checker_rejects_invalid_timestamp():
    patch = json.loads((repo_root() / "fixtures/patches/sample.patch.json").read_text())
    patch["created_at"] = "not-a-date"
    with pytest.raises(ValueError, match="patch/created_at:"):
        validate("patch", patch)


def test_unknown_schema_fails_explicitly():
    with pytest.raises(ValueError, match="Unknown schema"):
        validate("../not_a_schema", {})
