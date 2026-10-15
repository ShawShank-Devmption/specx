"""Validated seven-table report and dashboard data, with explicit incomplete inputs.

Run from any directory; relative CLI paths are repository-relative. Invalid inputs
exit 1 without publishing new output; missing/partial inputs publish with exit 2.
"""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict

from specx.client.io import read_json, read_jsonl
from specx.client.paths import repo_root
from specx.evalx.benchmark_store import atomic_json
from specx.evalx.tasks import load_tasks
from specx.optim.reviser import Arm
from specx.stats.extract import generation_table, verification_table
from specx.stats.report_inputs import stage_metrics, validate_inputs
from specx.stats.report_readiness import readiness
from specx.stats.report_safety import safety_checks
from specx.stats.report_tables import TITLES, render_report

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


class Numbers(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    schema_version: int = 1
    generated_at: str
    git_sha: str
    complete: bool
    execution: str
    models: dict[str, list[str]]
    n: dict[str, dict[str, int]]
    t1_generation: list[dict[str, Any]]
    t2_verification: list[dict[str, Any]]
    t3_s6: dict[str, Any] | None
    t4_s1: dict[str, Any] | None
    t5_s2: dict[str, Any] | None
    t6_f2: dict[str, Any] | None
    t7_readiness: dict[str, Any]
    quarantine: list[dict[str, Any]]
    revisions: list[dict[str, Any]]
    table_issues: dict[str, list[str]]
    missing: list[str]
    warnings: list[str]
    notes: list[str]
    provenance: dict[str, Any]


def _metadata(results: Path, stage: str) -> dict[str, Any]:
    path = results / stage / "run.json"
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected run metadata object in {path}")
    return data


def build_numbers(
    results: Path, *, apps: list[str], trials: int = 5, seed: int = 0
) -> dict[str, Any]:
    if not apps or len(set(apps)) != len(apps) or not set(apps) <= {"shop", "admin"}:
        raise ValueError("Choose unique supported apps")
    if trials < 1 or seed < 0:
        raise ValueError("Require positive trials and non-negative seed")
    validate_inputs(results)
    issues: dict[str, list[str]] = {key: [] for key in TITLES}
    warnings: list[str] = []
    files = [results / "tools" / f"{name}.tools.json" for name in apps]
    for path in files:
        if not path.exists() or not read_json(path):
            for key in ("t1_generation", "t2_verification"):
                issues[key].append(f"MISSING: {path} (nonempty generated tool set required)")
    available = [path for path in files if path.exists()]
    verdict_files = sorted((results / "verdicts").glob("*.jsonl"))
    f1 = results / "verdicts/f1.jsonl"
    if not f1.exists() or not read_jsonl(f1):
        issues["t2_verification"].append(f"MISSING: {f1} (verification evidence)")
    generation, verification = (
        generation_table(available),
        verification_table(available, verdict_files),
    )
    safety = {}
    for stage, key in (("s6", "t3_s6"), ("s1", "t4_s1"), ("s2", "t5_s2")):
        safety[key] = stage_metrics(results, stage, issues[key])
        safety_checks(safety[key], stage, issues[key], results)
    f2 = stage_metrics(results, "f2", issues["t6_f2"])
    f2_run, eval_run = _metadata(results, "f2"), _metadata(results, "evalx")
    for stage, record, key in (("f2", f2_run, "t6_f2"), ("evalx", eval_run, "t7_readiness")):
        if record.get("status") != "complete":
            issues[key].append(f"MISSING: completed {results / stage / 'run.json'}")
    readiness_data, agents = readiness(
        results, apps, trials=trials, seed=seed, issues=issues["t7_readiness"], warnings=warnings
    )
    for stage, record in (("f2", f2_run), ("evalx", eval_run)):
        declared = record.get("models", {}).get("agent")
        if declared and agents and declared not in agents:
            raise ValueError(f"{stage} metadata contradicts readiness agent model")
    revisions, training_n = [], {}
    for name in apps:
        args = f2_run.get("args", {})
        selected = [
            task
            for task in load_tasks(name)
            if task.split == "train"
            and (args.get("task_ids") is None or task.task_id in args["task_ids"])
        ]
        training_n[name] = len(selected) * args.get("trials", 0)
        for arm in Arm:
            row = (f2 or {}).get("apps", {}).get(name, {}).get(arm.value)
            if not row or not row.get("success_by_iter") or not training_n[name]:
                issues["t6_f2"].append(
                    f"MISSING: {results / 'f2/metrics.json'} {name}/{arm.value} with training n>0"
                )
                continue
            for log in row.get("revisions", []):
                success = log.get("success") or {}
                revisions.append(
                    {
                        "app": name,
                        "arm": arm.value,
                        "iter": log["iter"],
                        "tool_id": log["tool_id"],
                        "accepted": log["accepted"],
                        "reason": log["reason"],
                        "p": success.get("p"),
                        "diff": success.get("diff"),
                    }
                )
    verdicts = [row for path in verdict_files for row in read_jsonl(path)]
    quarantine = [
        {
            "tool_id": tool["tool_id"],
            "app": tool["app"],
            "reasons": sorted(
                {
                    violation["category"]
                    for verdict in verdicts
                    if verdict["tool_id"] == tool["tool_id"]
                    for violation in verdict["violations"]
                }
            )
            or ["No recorded reason"],
        }
        for path in available
        for tool in read_json(path)
        if tool.get("status") == "quarantined"
    ]
    selections = eval_run.get("optimisation_selection", {})
    notes = []
    for name, choice in selections.items():
        note = choice.get("note", f"{name}: selected {choice.get('arm', 'unknown')}")
        if choice.get("no_accepted_patches"):
            note += " optimised == verified (no accepted patches; stochastic outcomes can differ)."
        notes.append(note)
    for name in apps:
        if name not in selections:
            issues["t7_readiness"].append(
                f"MISSING: {results / 'evalx/run.json'} optimisation_selection.{name}"
            )
    executions = {record["execution"] for record in (f2_run, eval_run) if record.get("execution")}
    execution = (
        next(iter(executions)) if len(executions) == 1 else "mixed" if executions else "unknown"
    )
    if execution != "real":
        warnings.append(
            f"Evidence is {execution}: these are not validated live experimental results."
        )
    if execution == "mixed":
        issues["t7_readiness"].append("MISSING: consistent live/test-double evidence provenance")
    models = {
        "agent": agents,
        "reviser": sorted(
            {f2_run["models"]["reviser"]} if f2_run.get("models", {}).get("reviser") else set()
        ),
        "tool_set_versions": sorted(
            {
                row["tool_set_version"]
                for condition in readiness_data["conditions"]
                for row in read_jsonl(results / "trials" / f"{condition}.jsonl")
            }
            if all(
                (results / "trials" / f"{condition}.jsonl").exists()
                for condition in readiness_data["conditions"]
            )
            else set()
        ),
    }
    missing = sorted({item for values in issues.values() for item in values})
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root(), text=True
    ).strip()
    return Numbers(
        generated_at=datetime.now(UTC).isoformat(),
        git_sha=git_sha,
        complete=not missing,
        execution=execution,
        models=models,
        n={
            condition: {name: row["n"] for name, row in per_app.items()}
            for condition, per_app in readiness_data["conditions"].items()
        },
        t1_generation=generation,
        t2_verification=verification,
        t3_s6=safety["t3_s6"],
        t4_s1=safety["t4_s1"],
        t5_s2=safety["t5_s2"],
        t6_f2=f2,
        t7_readiness=readiness_data,
        quarantine=quarantine,
        revisions=revisions,
        table_issues=issues,
        missing=missing,
        warnings=sorted(set(warnings)),
        notes=notes,
        provenance={
            "results_dir": str(results),
            "f2_training_n": training_n,
            "optimisation_selection": selections,
            "run_metadata": {"f2": f2_run, "evalx": eval_run},
        },
    ).model_dump(mode="json")


def write_report(
    results: Path,
    out: Path,
    *,
    apps: list[str] | None = None,
    trials: int = 5,
    seed: int = 0,
    dashboard_public: Path | None = None,
) -> tuple[dict[str, Any], int]:
    numbers = build_numbers(
        results.resolve(), apps=apps or ["shop", "admin"], trials=trials, seed=seed
    )
    decisions_path = repo_root() / "docs/DECISIONS.md"
    text = render_report(numbers, decisions_path.read_text() if decisions_path.exists() else "")
    atomic_json(out / "numbers.json", numbers)
    (out / "REPORT.md").write_text(text, encoding="utf-8")
    atomic_json((dashboard_public or repo_root() / "dashboard/public") / "numbers.json", numbers)
    return numbers, 0 if numbers["complete"] else 2


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


@app.command()
def main(
    results: Path = Path("results"),
    out: Path = Path("results/final"),
    apps: str = "shop,admin",
    trials: int = typer.Option(5, min=1),
    seed: int = typer.Option(0, min=0),
    dashboard_public: Path | None = None,
) -> None:
    """Publish seven result tables; missing inputs exit 2, invalid records exit 1."""
    try:
        numbers, status = write_report(
            _resolve(results),
            _resolve(out),
            apps=apps.split(","),
            trials=trials,
            seed=seed,
            dashboard_public=_resolve(dashboard_public) if dashboard_public else None,
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Report failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Report {'complete' if status == 0 else 'incomplete'}: {len(numbers['missing'])} missing inputs; {_resolve(out) / 'REPORT.md'}"
    )
    raise typer.Exit(status)


if __name__ == "__main__":
    app()
