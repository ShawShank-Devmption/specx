"""Resume validation and serialized trial/trace persistence for the benchmark runner.

Commit each trace atomically before appending its trial. A process lock prevents two
runners from writing the same results tree; worker writes also share a thread lock.
"""

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field

from specx.client.io import append_jsonl, read_json, read_jsonl
from specx.client.paths import repo_root, stage_dir, traces_dir, trials_path
from specx.client.schemas import validate
from specx.evalx.conditions import Condition, tool_set_version
from specx.evalx.tasks import Task


class TrialJob(BaseModel):
    task: Task
    condition: Condition
    seed: int
    tools: list[dict[str, Any]] = Field(default_factory=list)
    contracts: list[dict[str, Any]] | None = None
    optimisation_selection: dict[str, Any] | None = None

    @property
    def trial_id(self) -> str:
        return f"{self.task.task_id}.{self.condition.value}.s{self.seed}"

    def context(self, model: str, max_steps: int) -> dict[str, Any]:
        encoded = json.dumps(
            self.task.model_dump(exclude_none=True), sort_keys=True, allow_nan=False
        ).encode()
        context = {
            "task_hash": hashlib.sha256(encoded).hexdigest(),
            "agent_model": model,
            "tool_set_version": tool_set_version(self.task.app, self.tools, self.condition),
            "max_steps": min(max_steps, self.task.max_steps),
            "contracts_hash": hashlib.sha256(
                json.dumps(self.contracts, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
        }
        if self.optimisation_selection is not None:
            context["optimisation_selection"] = self.optimisation_selection
        return context


def atomic_json(path: Path, record: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n"
    )
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class TrialStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.completed = 0

    @contextmanager
    def writer(self) -> Iterator[None]:
        with (stage_dir("trials") / ".benchmark.lock").open("a", encoding="utf-8") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another benchmark is writing this results directory") from error
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def records(self, condition: Condition) -> dict[str, dict[str, Any]]:
        path = trials_path(condition.value)
        records = read_jsonl(path) if path.exists() else []
        indexed = {}
        for record in records:
            validate("trial_result", record)
            if record["condition"] != condition.value:
                raise ValueError(f"Wrong condition in {path}")
            if record["trial_id"] in indexed:
                raise ValueError(f"Duplicate trial_id in {path}: {record['trial_id']}")
            indexed[record["trial_id"]] = record
        return indexed

    def check_completed(
        self, job: TrialJob, record: dict[str, Any], model: str, max_steps: int
    ) -> None:
        expected = job.context(model, max_steps)
        if (
            record["agent_model"] != model
            or record["tool_set_version"] != expected["tool_set_version"]
            or record["task_id"] != job.task.task_id
            or record["app"] != job.task.app
            or record["seed"] != job.seed
            or record.get("split", job.task.split) != job.task.split
        ):
            raise ValueError(f"Resume model/tool/task context mismatch: {job.trial_id}")
        expected_path = traces_dir() / f"{job.trial_id}.json"
        configured = Path(record.get("trace_path", ""))
        actual = configured if configured.is_absolute() else repo_root() / configured
        if actual.resolve() != expected_path.resolve():
            raise ValueError(f"Missing or unexpected trace_path for {job.trial_id}")
        try:
            trace = read_json(actual)
        except (OSError, ValueError) as error:
            raise ValueError(f"Missing or invalid completed trace for {job.trial_id}") from error
        if (
            not isinstance(trace, dict)
            or trace.get("run_context") != expected
            or trace.get("trial_id") != job.trial_id
        ):
            raise ValueError(f"Resume trace context mismatch: {job.trial_id}")

    def save(
        self,
        job: TrialJob,
        trial: dict[str, Any],
        trace: dict[str, Any],
        model: str,
        max_steps: int,
    ) -> None:
        if trial["trial_id"] != job.trial_id or trace["trial_id"] != job.trial_id:
            raise ValueError("Episode returned an unexpected trial_id")
        trace_path = traces_dir() / f"{job.trial_id}.json"
        trial["trace_path"] = (
            str(trace_path.relative_to(repo_root()))
            if trace_path.is_relative_to(repo_root())
            else str(trace_path)
        )
        validate("trial_result", trial)
        trace["task"] = job.task.model_dump(exclude_none=True)
        trace["run_context"] = job.context(model, max_steps)
        trace["tool_calls"] = trace["step_log"]
        trace["verdict_run_ids"] = [verdict["run_id"] for verdict in trace["verdicts"]]
        with self._lock:
            atomic_json(trace_path, trace)
            path = trials_path(job.condition.value)
            # Existing valid JSONL need not have a trailing newline.
            if path.exists() and path.stat().st_size:
                with path.open("rb+") as stream:
                    stream.seek(-1, os.SEEK_END)
                    if stream.read(1) != b"\n":
                        stream.seek(0, os.SEEK_END)
                        stream.write(b"\n")
            append_jsonl(path, trial)
            self.completed += 1
