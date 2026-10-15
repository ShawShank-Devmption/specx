#!/usr/bin/env python3
"""Validate every fixture (and, if present, every results/ file) against contracts/*.schema.json.

Run: `uv run --with jsonschema python scripts/check_contracts.py` (or `make check-contracts`).
Exit 1 on the first invalid record, printing the JSON-pointer path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts"

# (glob relative to repo root, schema name, is_jsonl, is_array)
TARGETS = [
    ("fixtures/apps/*.app.json", "app_manifest", False, False),
    ("platform/seed-apps/*/app.json", "app_manifest", False, False),
    ("fixtures/tools/*.tools.json", "tool_definition", False, True),
    ("results/tools/*.tools.json", "tool_definition", False, True),
    ("fixtures/contracts/*.contracts.json", "contract", False, True),
    ("results/contracts/*.contracts.json", "contract", False, True),
    ("fixtures/events/*.jsonl", "event_record", True, False),
    ("fixtures/verdicts/*.jsonl", "verdict", True, False),
    ("results/verdicts/*.jsonl", "verdict", True, False),
    ("fixtures/graphs/*.graph.json", "workflow_graph", False, False),
    ("results/graphs/*.graph.json", "workflow_graph", False, False),
    ("fixtures/trials/*.jsonl", "trial_result", True, False),
    ("results/trials/*.jsonl", "trial_result", True, False),
    ("fixtures/patches/*.patch.json", "patch", False, False),
    ("results/patches/*.patch.json", "patch", False, False),
    ("fixtures/tasks/*.tasks.json", "task", False, True),
    ("python/specx/evalx/tasks/*.tasks.json", "task", False, True),
]


def load_validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def check(validator: Draft202012Validator, obj: object, where: str) -> None:
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    if errors:
        e = errors[0]
        path = "/" + "/".join(str(p) for p in e.absolute_path)
        print(f"INVALID {where} at {path}: {e.message}")
        sys.exit(1)


def main() -> None:
    validators = {}
    n_files = n_records = 0
    for pattern, schema_name, is_jsonl, is_array in TARGETS:
        v = validators.setdefault(schema_name, load_validator(schema_name))
        for path in sorted(ROOT.glob(pattern)):
            n_files += 1
            if is_jsonl:
                for i, line in enumerate(path.read_text().splitlines(), 1):
                    if line.strip():
                        check(v, json.loads(line), f"{path.relative_to(ROOT)}:{i}")
                        n_records += 1
            else:
                data = json.loads(path.read_text())
                items = data if is_array else [data]
                if is_array and not isinstance(data, list):
                    print(f"INVALID {path}: expected a JSON array")
                    sys.exit(1)
                for i, item in enumerate(items):
                    check(v, item, f"{path.relative_to(ROOT)}[{i}]")
                    n_records += 1
    print(f"OK: {n_records} records in {n_files} files validate against {len(validators)} schemas")


if __name__ == "__main__":
    main()
