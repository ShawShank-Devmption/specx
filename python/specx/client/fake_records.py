"""Construct schema-validated records for the offline sandbox.

These are test doubles, not a replacement for Dev A's executable contract engine.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from specx.client.schemas import validate


class ClauseResult(BaseModel):
    clause_id: str
    kind: str
    surface: str
    passed: bool | None
    observed: Any = None
    expected: Any = None


class Violation(BaseModel):
    clause_id: str
    severity: Literal["low", "medium", "high"] = "high"
    signature: str
    category: str


class EffectDiff(BaseModel):
    db: dict[str, dict[str, int]] = Field(default_factory=dict)
    network: list[dict[str, Any]] = Field(default_factory=list)
    dom: dict[str, Any] = Field(default_factory=lambda: {"mutations": 0})
    storage: list[dict[str, Any]] = Field(default_factory=list)
    audit: list[dict[str, Any]] = Field(default_factory=list)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    session_id: str
    app: str
    tool_id: str
    tool_version: int
    metadata_revision: int
    args: dict[str, Any]
    mode: str = "single"
    concurrency_group: str | None = None
    sequence_prefix: list[str]
    started_at: str
    duration_ms: float
    status: str = "pass"
    output: Any = None
    clause_results: list[ClauseResult] = Field(default_factory=list)
    effect_diff: EffectDiff = Field(default_factory=EffectDiff)
    violations: list[Violation] = Field(default_factory=list)
    anomaly: dict[str, Any] | None = None
    source: str

    def record(self) -> dict[str, Any]:
        result = self.model_dump()
        if self.concurrency_group is None:
            del result["concurrency_group"]
        validate("verdict", result)
        return result


class EventRecord(BaseModel):
    session_id: str
    run_id: str
    seq: int
    t_ms: float
    phase: str
    kind: str
    data: dict[str, Any]

    def record(self) -> dict[str, Any]:
        result = self.model_dump()
        validate("event_record", result)
        return result


def fail(
    verdict: Verdict,
    clause_id: str,
    kind: str,
    category: str,
    observed: Any,
    expected: Any,
    *,
    surface: str = "db",
) -> None:
    verdict.status = "fail"
    verdict.clause_results = [c for c in verdict.clause_results if c.clause_id != clause_id]
    verdict.clause_results.append(
        ClauseResult(
            clause_id=clause_id,
            kind=kind,
            surface=surface,
            passed=False,
            observed=observed,
            expected=expected,
        )
    )
    verdict.violations.append(
        Violation(
            clause_id=clause_id,
            category=category,
            signature=f"{verdict.tool_id}|{clause_id}|{kind}|{observed}",
        )
    )


def db_diff(
    before: dict[str, list[dict[str, Any]]], after: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, int]]:
    result = {}
    for table in sorted(before.keys() | after.keys()):
        old = {row["id"]: row for row in before.get(table, [])}
        new = {row["id"]: row for row in after.get(table, [])}
        counts = {
            "inserted": len(new.keys() - old.keys()),
            "deleted": len(old.keys() - new.keys()),
            "updated": sum(old[key] != new[key] for key in old.keys() & new.keys()),
        }
        if any(counts.values()):
            result[table] = counts
    return result
