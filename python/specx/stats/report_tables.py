"""Render the seven shared-number tables, never substituting zeros for missing cells."""

import json
from typing import Any

import pandas as pd

from specx.stats.report_inputs import metric_rows

TITLES = {
    "t1_generation": "Table 1 - Generation",
    "t2_verification": "Table 2 - Verification",
    "t3_s6": "Table 3 - S6 anomaly detection",
    "t4_s1": "Table 4 - S1 adversarial fuzzing",
    "t5_s2": "Table 5 - S2 risk prediction",
    "t6_f2": "Table 6 - F2/S4 optimisation",
    "t7_readiness": "Table 7 - F4 readiness",
}


def _cell(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def markdown_table(rows: list[dict[str, Any]]) -> str:
    rows = rows or [{"status": "No observations"}]
    return str(
        pd.DataFrame([{key: _cell(value) for key, value in row.items()} for row in rows])
        .fillna("unknown")
        .to_markdown(index=False, disable_numparse=True)
    )


def readiness_rows(numbers: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for condition, apps in numbers["t7_readiness"]["conditions"].items():
        for name, row in apps.items():

            def estimate(metric: str, percent: bool = False, row: dict[str, Any] = row) -> str:
                value = row[metric]
                if value is None:
                    return "MISSING"
                scale = 100 if percent else 1
                low, high = row[f"{metric}_ci"]
                return f"{value * scale:.2f} [{low * scale:.2f}, {high * scale:.2f}]"

            rows.append(
                {
                    "app": name,
                    "condition": condition,
                    "n": row["n"],
                    "success % [95% CI]": estimate("success_rate", True),
                    "steps [95% CI]": estimate("mean_steps"),
                    "tokens [95% CI]": estimate("mean_tokens"),
                    "policy % [95% CI]": estimate("policy_violation_rate", True),
                    "unapproved calls": row["unapproved_calls"] if row["n"] else None,
                    "quarantined calls": row["quarantined_tool_calls"] if row["n"] else None,
                }
            )
    return rows


def render_table(numbers: dict[str, Any], key: str) -> str:
    if key == "t7_readiness":
        rows = readiness_rows(numbers)
    elif key == "t6_f2":
        rows = [
            {
                "app": name,
                "arm": arm,
                "n_train": numbers["provenance"]["f2_training_n"].get(name),
                **{
                    field: row.get(field)
                    for field in (
                        "success_by_iter",
                        "iterations_to_convergence",
                        "proposed",
                        "accepted",
                        "rejected",
                    )
                },
            }
            for name, arms in (numbers[key] or {}).get("apps", {}).items()
            for arm, row in arms.items()
        ]
    elif key in ("t1_generation", "t2_verification"):
        rows = numbers[key]
    else:
        rows = metric_rows(numbers[key]) if numbers[key] is not None else []
    issues = numbers["table_issues"][key]
    table = markdown_table(rows)
    if issues:
        table += "\n\n" + markdown_table([{"status": issue} for issue in issues])
    if key == "t7_readiness":
        table += "\n\nPaired comparisons (B minus A; two-sided tests):\n\n" + markdown_table(
            [
                {
                    field: row[field]
                    for field in (
                        "app",
                        "from_condition",
                        "to_condition",
                        "metric",
                        "n",
                        "diff",
                        "ci_low",
                        "ci_high",
                        "p",
                        "p_holm",
                        "effect",
                        "effect_name",
                        "holm_family",
                    )
                }
                for row in numbers[key]["comparisons"]
            ]
        )
    return table


def render_report(numbers: dict[str, Any], decisions: str) -> str:
    header = (
        f"# SpecX results\n\nGenerated: {numbers['generated_at']} · Git: {numbers['git_sha']}\n\n"
        f"Status: {'COMPLETE INPUTS' if numbers['complete'] else 'INCOMPLETE'} · Evidence: {numbers['execution']}\n\n"
        f"Models/versions: {_cell(numbers['models'])}\n\n"
        "Bootstrap CIs: 2,000 paired resamples, local seed 0. Holm correction uses one family per metric across apps and adjacent conditions. "
        "Missing pairs are dropped symmetrically; n is the actual matched count. Safety and task success are separate outcomes.\n\n"
    )
    notes = "\n".join(f"- {note}" for note in numbers["notes"] + numbers["warnings"])
    tables = "\n\n".join(
        f"## {title}\n\n{render_table(numbers, key)}" for key, title in TITLES.items()
    )
    return (
        header
        + (notes + "\n\n" if notes else "")
        + tables
        + "\n\n## Deviations from plan\n\n"
        + (decisions.rstrip() or "No decisions document provided.")
        + "\n"
    )
