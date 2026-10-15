"""Tables 1-2 from schema-validated tool sets and verification verdicts.

Replay matching follows F1's documented replay-of-last-single protocol; unmatched
replays stay unknown rather than being labelled deterministic just because they pass.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from specx.client.io import read_json, read_jsonl
from specx.client.schemas import validate


class GenerationRow(BaseModel):
    app: str
    tools_generated: int
    mean_provenance_surfaces: float | None
    tools_ge3_surfaces: int


class VerificationRow(BaseModel):
    app: str
    verified: int
    quarantined: int
    unverifiable: int
    generated: int
    quarantine_reasons: dict[str, int]
    replay_determinism_rate: float | None
    replay_n: int
    replay_total: int
    replay_unmatched: int


def _tools(files: Sequence[Path]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen = set()
    for path in files:
        records = read_json(path)
        if not isinstance(records, list):
            raise ValueError(f"Expected tool array in {path}")
        if not records:
            grouped.setdefault(path.name.split(".", 1)[0], [])
        for record in records:
            validate("tool_definition", record)
            if record["tool_id"] in seen:
                raise ValueError(f"Duplicate tool_id: {record['tool_id']}")
            seen.add(record["tool_id"])
            grouped.setdefault(record["app"], []).append(record)
    return grouped


def generation_table(tools_files: Sequence[Path]) -> list[dict[str, Any]]:
    rows = []
    for app, tools in sorted(_tools(tools_files).items()):
        counts = [len({item["surface"] for item in tool["provenance"]}) for tool in tools]
        rows.append(
            GenerationRow(
                app=app,
                tools_generated=len(tools),
                mean_provenance_surfaces=sum(counts) / len(counts) if counts else None,
                tools_ge3_surfaces=sum(count >= 3 for count in counts),
            ).model_dump()
        )
    return rows


def _verdicts(files: Sequence[Path]) -> list[dict[str, Any]]:
    records = []
    seen = set()
    for path in files:
        for record in read_jsonl(path):
            validate("verdict", record)
            if record["run_id"] in seen:
                raise ValueError(f"Duplicate run_id: {record['run_id']}")
            seen.add(record["run_id"])
            records.append(record)
    return sorted(
        records,
        key=lambda record: datetime.fromisoformat(record["started_at"].replace("Z", "+00:00")),
    )


def _replay_key(verdict: dict[str, Any]) -> tuple[Any, ...]:
    return (
        verdict["app"],
        verdict["session_id"],
        verdict["tool_id"],
        verdict.get("tool_version"),
        verdict.get("metadata_revision"),
        verdict["source"],
        json.dumps(verdict["args"], sort_keys=True),
    )


def _replays(verdicts: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    previous = {}
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "matched": 0, "same": 0})
    for verdict in verdicts:
        if verdict["source"] != "f1":
            continue
        key = _replay_key(verdict)
        if verdict["mode"] == "single":
            previous[key] = verdict
        elif verdict["mode"] == "replay":
            record = stats[verdict["app"]]
            record["total"] += 1
            original = previous.get(key)
            if original is None:
                continue
            record["matched"] += 1
            before_clauses = {
                clause["clause_id"]: clause["passed"] for clause in original["clause_results"]
            }
            after_clauses = {
                clause["clause_id"]: clause["passed"] for clause in verdict["clause_results"]
            }
            record["same"] += (
                original["effect_diff"]["db"] == verdict["effect_diff"]["db"]
                and before_clauses == after_clauses
            )
    return stats


def verification_table(
    tools_files: Sequence[Path], verdict_files: Sequence[Path]
) -> list[dict[str, Any]]:
    verdicts = _verdicts(verdict_files)
    by_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for verdict in verdicts:
        by_tool[verdict["tool_id"]].append(verdict)
    replay_stats = _replays(verdicts)
    rows = []
    for app, tools in sorted(_tools(tools_files).items()):
        statuses: Counter[str] = Counter()
        reasons: dict[str, set[str]] = defaultdict(set)
        for tool in tools:
            status = tool.get("status", "generated")
            if status == "generated" and any(
                verdict["status"] == "unverifiable"
                or any(clause["passed"] is None for clause in verdict["clause_results"])
                for verdict in by_tool[tool["tool_id"]]
            ):
                status = "unverifiable"
            statuses[status] += 1
            if status == "quarantined":
                for verdict in by_tool[tool["tool_id"]]:
                    for violation in verdict["violations"]:
                        reasons[violation.get("category", "unspecified")].add(tool["tool_id"])
        replay = replay_stats.get(app, {"total": 0, "matched": 0, "same": 0})
        rows.append(
            VerificationRow(
                app=app,
                verified=statuses["verified"],
                quarantined=statuses["quarantined"],
                unverifiable=statuses["unverifiable"],
                generated=statuses["generated"],
                quarantine_reasons={
                    category: len(ids) for category, ids in sorted(reasons.items())
                },
                replay_determinism_rate=replay["same"] / replay["matched"]
                if replay["matched"]
                else None,
                replay_n=replay["matched"],
                replay_total=replay["total"],
                replay_unmatched=replay["total"] - replay["matched"],
            ).model_dump()
        )
    return rows
