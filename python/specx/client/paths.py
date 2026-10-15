"""Resolve published artefacts from the repository, independently of the caller's cwd.

Only output directories are created; requesting a file path never creates an empty file.
"""

import os
import re
from pathlib import Path


def repo_root() -> Path:
    """Find the checkout containing this package and its integration contracts."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "contracts").is_dir():
            return parent
    raise FileNotFoundError("Cannot locate the SpecX repository (contracts/ is missing)")


def results_dir() -> Path:
    configured = Path(os.environ.get("SPECX_RESULTS_DIR", "results")).expanduser()
    path = configured if configured.is_absolute() else repo_root() / configured
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
        raise ValueError(f"Invalid artefact name: {value!r}")
    return value


def stage_dir(name: str) -> Path:
    path = results_dir() / _component(name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def tools_path(app: str, variant: str | None = None) -> Path:
    suffix = f".{_component(variant)}" if variant is not None else ""
    return stage_dir("tools") / f"{_component(app)}{suffix}.tools.json"


def contracts_path(app: str) -> Path:
    return stage_dir("contracts") / f"{_component(app)}.contracts.json"


def verdicts_path(source: str) -> Path:
    return stage_dir("verdicts") / f"{_component(source)}.jsonl"


def graphs_dir() -> Path:
    return stage_dir("graphs")


def trials_path(condition_or_name: str) -> Path:
    return stage_dir("trials") / f"{_component(condition_or_name)}.jsonl"


def traces_dir() -> Path:
    return stage_dir("traces")


def patches_dir() -> Path:
    return stage_dir("patches")
