"""Check benchmark definitions and mechanical, conjunctive success evaluation."""

from copy import deepcopy
from typing import Any

import pytest

from specx.client import FakeSandbox
from specx.client.io import read_json
from specx.client.paths import repo_root
from specx.client.schemas import validate
from specx.evalx.tasks import Task, check_success, load_tasks


class SnapshotClient:
    def __init__(self, state: dict[str, Any]) -> None:
        self.snapshot = state
        self.calls = 0

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]:
        self.calls += 1
        return deepcopy(self.snapshot)


def state_for(table: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"db": {table: {"count": len(rows), "rows": rows}}, "url": "/users", "aria": "Users"}


@pytest.mark.parametrize("app", ["shop", "admin"])
def test_twenty_tasks_validate_and_splits_are_fixed(app: str) -> None:
    tasks = load_tasks(app)
    assert len(tasks) == 10
    assert {task.task_id for task in tasks} == {f"{app}.t{i:02}" for i in range(1, 11)}
    assert {task.task_id for task in tasks if task.split == "train"} == {
        f"{app}.t{i:02}" for i in range(2, 7)
    }
    for task in tasks:
        validate("task", task.model_dump(exclude_none=True))


def test_schema_preserves_legacy_checks_and_validates_compound_checks() -> None:
    legacy = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[0]
    validate("task", legacy)
    assert "success_checks" not in legacy
    compound = {**legacy, "success_checks": [legacy["success_check"]]}
    validate("task", compound)
    for invalid in (None, {}, [], [{"kind": "unsupported"}], ["not a check"]):
        with pytest.raises(ValueError, match="task/success_checks"):
            validate("task", {**legacy, "success_checks": invalid})


def test_shop_t02_on_fake_sandbox() -> None:
    task = next(task for task in load_tasks("shop") if task.task_id == "shop.t02")
    with FakeSandbox() as client:
        session = client.create_session("shop")
        assert not check_success(task, client, session)
        client.invoke(session, "shop.add_to_cart", {"product_id": 2, "qty": 1}, source="f4")
        assert check_success(task, client, session)


def test_admin_t10_has_explicit_dana_setup_and_requires_both_goals() -> None:
    task = next(task for task in load_tasks("admin") if task.task_id == "admin.t10")
    assert task.setup == {
        "users": [{"username": "dana", "email": "dana@example.com", "role": "viewer", "active": 1}]
    }
    client = SnapshotClient(
        state_for(
            "users",
            [
                {"id": 2, "username": "bob", "active": 0, "role": "editor"},
                {"id": 7, "username": "dana", "active": 1, "role": "viewer"},
            ],
        )
    )
    assert not check_success(task, client, "s1")
    client.snapshot["db"]["users"]["rows"][1]["role"] = "admin"
    assert check_success(task, client, "s1")
    client.snapshot["db"]["users"]["rows"][0]["active"] = 1
    assert not check_success(task, client, "s1")
    assert client.calls == 3  # one consistent state snapshot per evaluation


def test_every_extra_check_must_pass_not_just_the_first() -> None:
    raw = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[0]
    raw["success_checks"] = [
        {"kind": "db_count", "table": "orders", "expect_min": 1},
        {"kind": "url_contains", "value": "/orders"},
    ]
    client = SnapshotClient(state_for("orders", [{"id": 1, "status": "placed"}]))
    assert not check_success(raw, client, "s1")
    client.snapshot["url"] = "/orders"
    assert check_success(raw, client, "s1")
    client.snapshot["db"]["orders"]["rows"][0]["status"] = "pending"
    assert not check_success(raw, client, "s1")  # primary check still applies


def test_shop_checkout_checks_ordered_product_and_quantity() -> None:
    task = next(task for task in load_tasks("shop") if task.task_id == "shop.t01")
    with FakeSandbox() as client:
        session = client.create_session("shop")
        client.invoke(session, "shop.add_to_cart", {"product_id": 1, "qty": 1}, source="f4")
        client.invoke(session, "shop.place_order", {"confirm": True}, source="f4")
        assert not check_success(task, client, session)
        client.reset(session)
        client.invoke(session, "shop.add_to_cart", {"product_id": 1, "qty": 2}, source="f4")
        client.invoke(session, "shop.place_order", {"confirm": True}, source="f4")
        assert check_success(task, client, session)


def test_cart_goals_require_both_products() -> None:
    task = next(task for task in load_tasks("shop") if task.task_id == "shop.t06")
    with FakeSandbox() as client:
        session = client.create_session("shop")
        for _ in range(2):
            client.invoke(session, "shop.add_to_cart", {"product_id": 1, "qty": 1}, source="f4")
        assert not check_success(task, client, session)
        client.reset(session)
        for product_id in (1, 2):
            client.invoke(
                session, "shop.add_to_cart", {"product_id": product_id, "qty": 1}, source="f4"
            )
        assert check_success(task, client, session)


def test_named_product_equality_resolves_via_products() -> None:
    raw = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[1]
    raw["success_check"]["where"]["product_id"] = "Red Notebook"
    with FakeSandbox() as client:
        session = client.create_session("shop")
        client.invoke(session, "shop.add_to_cart", {"product_id": 2, "qty": 1}, source="f4")
        assert check_success(raw, client, session)


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        ("url_contains", "/users", True),
        ("url_contains", "/orders", False),
        ("dom_text", "Users", True),
        ("dom_text", "Missing", False),
    ],
)
def test_url_and_dom_checks(kind: str, value: str, expected: bool) -> None:
    raw = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[0]
    raw["success_check"] = {"kind": kind, "value": value}
    assert check_success(raw, SnapshotClient(state_for("users", [])), "s1") is expected


def test_empty_table_is_success_but_missing_table_is_an_error() -> None:
    task = next(task for task in load_tasks("admin") if task.task_id == "admin.t08")
    assert check_success(task, SnapshotClient(state_for("users", [])), "s1")
    with pytest.raises(ValueError, match="users"):
        check_success(task, SnapshotClient({"db": {}}), "s1")


def test_missing_filter_column_cannot_match_null() -> None:
    raw = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[1]
    raw["success_check"]["where"] = {"missing": None}
    assert not check_success(raw, SnapshotClient(state_for("cart_items", [{"id": 1}])), "s1")


def test_check_configuration_errors_are_explicit() -> None:
    raw = read_json(repo_root() / "fixtures/tasks/shop.tasks.json")[0]
    raw["success_check"] = {"kind": "db_query", "table": "orders"}
    with pytest.raises(ValueError, match=r"expect_count|expect_min"):
        Task.model_validate(raw)


@pytest.mark.parametrize("app", ["../shop", "/shop", "", "unknown"])
def test_task_loader_rejects_unknown_or_unsafe_app_names(app: str) -> None:
    with pytest.raises(ValueError, match="app"):
        load_tasks(app)
