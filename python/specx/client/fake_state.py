"""In-memory shop state and canned action semantics for fixture-driven tests.

Never evaluates JavaScript or claims to enforce arbitrary executable contracts.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from specx.client.sandbox import SandboxError


@dataclass
class FakeSession:
    app: str
    seed: int
    tools: dict[str, dict[str, Any]]
    contracts: list[dict[str, Any]]
    db: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    storage: dict[str, dict[str, Any]] = field(default_factory=lambda: {"local": {}, "session": {}})
    leak: dict[str, Any] | None = None
    url: str = "http://127.0.0.1:5101/products"

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(
            {
                "db": self.db,
                "storage": self.storage,
                "url": self.url,
                "history": self.history,
                "leak": self.leak,
            }
        )

    def restore(self, snapshot: dict[str, Any]) -> None:
        for key, value in deepcopy(snapshot).items():
            setattr(self, key, value)


def seed_db() -> dict[str, list[dict[str, Any]]]:
    products = [
        ("Blue Mug", 1299),
        ("Red Notebook", 499),
        ("Green Pen", 199),
        ("Black Lamp", 2599),
        ("White Chair", 7999),
    ]
    return {
        "products": [
            {"id": i, "name": name, "price_cents": price, "stock": 10}
            for i, (name, price) in enumerate(products, 1)
        ],
        "users": [{"id": 1, "username": "alice", "address": "Saved address"}],
        "cart_items": [],
        "orders": [],
        "order_items": [],
        "notes": [],
        "audit_log": [],
    }


def next_id(rows: list[dict[str, Any]]) -> int:
    return max((row["id"] for row in rows), default=0) + 1


def product(session: FakeSession, product_id: int) -> dict[str, Any] | None:
    return next((row for row in session.db["products"] if row["id"] == product_id), None)


def action_for(tool: dict[str, Any]) -> str:
    """Dispatch by immutable ID, not the revisable agent-facing name."""
    return str(tool["tool_id"]).split(".", 1)[1]


def perform(session: FakeSession, action: str, args: dict[str, Any]) -> tuple[Any, str | None]:
    if action == "list_products":
        return {"products": deepcopy(session.db["products"])}, None
    if action == "get_product":
        return deepcopy(product(session, args["product_id"])), None
    if action == "view_cart":
        return {
            "items": deepcopy(session.db["cart_items"]),
            "total_cents": cart_total(session),
        }, None
    if action == "list_orders":
        return {"orders": deepcopy(session.db["orders"])}, None
    if action == "add_to_cart":
        item = {
            "id": next_id(session.db["cart_items"]),
            "user_id": 1,
            "product_id": args["product_id"],
            "qty": args["qty"],
        }
        session.db["cart_items"].append(item)
        selected = product(session, args["product_id"])
        assert selected is not None
        # Deliberately reproduce the documented missing stock check.
        selected["stock"] -= args["qty"]
        return {"cart_item_id": item["id"], "cart_total_cents": cart_total(session)}, "cart.add"
    if action == "remove_from_cart":
        session.db["cart_items"] = [
            row for row in session.db["cart_items"] if row["product_id"] != args["product_id"]
        ]
        return {"ok": True}, "cart.remove"
    if action == "place_order":
        order = {
            "id": next_id(session.db["orders"]),
            "user_id": 1,
            "total_cents": cart_total(session),
            "status": "placed",
            "created_at": "2026-10-15T00:00:00Z",
        }
        session.db["orders"].append(order)
        for item in session.db["cart_items"]:
            selected = product(session, item["product_id"])
            assert selected is not None
            session.db["order_items"].append(
                {
                    "id": next_id(session.db["order_items"]),
                    "order_id": order["id"],
                    "product_id": item["product_id"],
                    "qty": item["qty"],
                    "price_cents": selected["price_cents"],
                }
            )
        session.db["cart_items"] = []
        return {"order_id": order["id"], "total_cents": order["total_cents"]}, "order.place"
    raise SandboxError("unsupported_fake_action", f"No canned behavior for {action!r}")


def cart_total(session: FakeSession) -> int:
    prices = {row["id"]: row["price_cents"] for row in session.db["products"]}
    return sum(prices[row["product_id"]] * row["qty"] for row in session.db["cart_items"])
