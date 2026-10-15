"""Load benchmark tasks and evaluate final-state success mechanically.

The legacy primary check always applies. Optional extra checks are conjunctive
and use the same snapshot, preventing partial completion from counting as success.
"""

import re
from pathlib import Path
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from specx.client.io import read_json
from specx.client.schemas import validate


class SuccessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["db_query", "db_count", "url_contains", "dom_text"]
    table: str | None = None
    where: dict[str, Any] | None = None
    expect_count: int | None = None
    expect_min: int | None = None
    value: str | None = None

    @model_validator(mode="after")
    def check_configuration(self) -> Self:
        if self.kind in ("db_query", "db_count"):
            if not self.table:
                raise ValueError("Database success checks require a table")
            if self.expect_count is None and self.expect_min is None:
                raise ValueError("Database success checks require expect_count or expect_min")
        elif not self.value:
            raise ValueError("URL/DOM success checks require a non-empty value")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task_id: str
    app: str
    instruction: str
    split: Literal["train", "heldout"]
    setup: dict[str, Any] | None = None
    success_check: SuccessCheck
    success_checks: list[SuccessCheck] | None = Field(default=None, min_length=1)
    policy: list[
        Literal[
            "never_delete",
            "no_checkout_without_confirm",
            "no_role_change",
            "stay_in_app",
            "read_only",
        ]
    ]
    max_steps: int = Field(ge=1, le=40)
    notes: str | None = None


class StateClient(Protocol):
    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]: ...


def load_tasks(app: str) -> list[Task]:
    """Load one app's task corpus without creating directories or mutating state."""
    if not re.fullmatch(r"[a-z0-9_]+", app):
        raise ValueError(f"Invalid app name: {app!r}")
    path = Path(__file__).with_suffix("") / f"{app}.tasks.json"
    if not path.is_file():
        raise ValueError(f"No tasks defined for app {app!r}")
    records = read_json(path)
    if not isinstance(records, list):
        raise ValueError(f"Expected a task array in {path}")
    tasks = []
    seen = set()
    for record in records:
        validate("task", record)
        task = Task.model_validate(record)
        if task.app != app or not task.task_id.startswith(f"{app}."):
            raise ValueError(f"Task {task.task_id!r} does not belong to app {app!r}")
        if task.task_id in seen:
            raise ValueError(f"Duplicate task_id: {task.task_id}")
        seen.add(task.task_id)
        tasks.append(task)
    return tasks


def _rows(state: dict[str, Any], table: str) -> list[dict[str, Any]]:
    db = state.get("db")
    data = db.get(table) if isinstance(db, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        # Missing observability must not accidentally satisfy an expect_count=0 goal.
        raise ValueError(f"State is missing rows for table {table!r}")
    return rows


def _matches(row: dict[str, Any], where: dict[str, Any], state: dict[str, Any]) -> bool:
    for column, expected in where.items():
        if column == "product_id" and isinstance(expected, str):
            products = [
                product for product in _rows(state, "products") if product.get("name") == expected
            ]
            if len(products) != 1 or "id" not in products[0]:
                raise ValueError(f"Product name must resolve uniquely: {expected!r}")
            expected = products[0]["id"]
        if column not in row or row[column] != expected:
            return False
    return True


def _passes(check: SuccessCheck, state: dict[str, Any]) -> bool:
    if check.kind in ("db_query", "db_count"):
        assert check.table is not None
        count = sum(_matches(row, check.where or {}, state) for row in _rows(state, check.table))
        return (check.expect_count is None or count == check.expect_count) and (
            check.expect_min is None or count >= check.expect_min
        )
    field = "url" if check.kind == "url_contains" else "aria"
    observed = state.get(field)
    if not isinstance(observed, str):
        raise ValueError(f"State is missing {field!r} for {check.kind}")
    assert check.value is not None
    return check.value in observed


def check_success(task: Task | dict[str, Any], client: StateClient, session_id: str) -> bool:
    """Evaluate primary AND additional checks, without applying setup or taking actions.

    The runner owns reset/apply. DB checks use equality filters and exact/minimum row
    counts; product_id filters may name a product. dom_text checks the API's ARIA text.
    """
    record = task.model_dump(exclude_none=True) if isinstance(task, Task) else task
    validate("task", record)
    parsed = Task.model_validate(record)
    state = client.state(session_id)
    return all(
        _passes(check, state) for check in [parsed.success_check, *(parsed.success_checks or [])]
    )
