"""Deterministic, isolated shop sandbox implementing the shared client interface.

Fixture-backed canned actions reproduce C1 defects; arbitrary handlers are not executed.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlsplit

from specx.client.fake_execution import apply_leak, emit_event, execute, precheck
from specx.client.fake_records import Verdict, db_diff, fail
from specx.client.fake_state import FakeSession, action_for, product, seed_db
from specx.client.io import read_json
from specx.client.paths import repo_root
from specx.client.sandbox import SandboxClient, SandboxError
from specx.client.schemas import validate


class FakeSandbox(SandboxClient):
    def __init__(self, base_url: str | None = None) -> None:
        # No HTTP client is needed, and nothing is written to results/ by offline tests.
        self.base_url = base_url or "http://127.0.0.1:4000"
        self._sessions: dict[str, FakeSession] = {}
        self._session_counter = 0
        self._run_counter = 0
        self._group_counter = 0
        self._tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
        self._contracts = read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
        for tool in self._tools:
            validate("tool_definition", tool)
        for contract in self._contracts:
            validate("contract", contract)

    def shutdown(self) -> None:
        self._sessions.clear()

    def _session(self, session_id: str) -> FakeSession:
        if session_id not in self._sessions:
            raise SandboxError("unknown_session", session_id)
        return self._sessions[session_id]

    def health(self) -> dict[str, Any]:
        return {"ok": True, "apps": ["shop"], "sessions": len(self._sessions)}

    def create_session(
        self, app: str, seed: int | None = None, leak: dict[str, Any] | None = None
    ) -> str:
        if app != "shop":
            raise SandboxError(
                "unknown_app", f"FakeSandbox has fixtures for shop only, got {app!r}"
            )
        self._session_counter += 1
        session_id = f"s_fake{self._session_counter:04d}"
        self._sessions[session_id] = FakeSession(
            app=app,
            seed=seed or 0,
            tools={tool["tool_id"]: deepcopy(tool) for tool in self._tools},
            contracts=deepcopy(self._contracts),
            db=seed_db(),
        )
        if leak is not None:
            self.inject_leak(session_id, leak["kind"], leak["delay_ms"])
        return session_id

    def load_tools(
        self, session_id: str, tools: list[dict[str, Any]], contracts: list[dict[str, Any]]
    ) -> None:
        session = self._session(session_id)
        for schema, records in (("tool_definition", tools), ("contract", contracts)):
            for record in records:
                validate(schema, record)
        if any(tool["app"] != session.app for tool in tools):
            raise SandboxError("wrong_app", "Tools must belong to the session app")
        session.tools = {tool["tool_id"]: deepcopy(tool) for tool in tools}
        session.contracts = deepcopy(contracts)

    def reset(self, session_id: str, seed: int | None = None) -> None:
        session = self._session(session_id)
        self._sessions[session_id] = FakeSession(
            app=session.app,
            seed=session.seed if seed is None else seed,
            tools=session.tools,
            contracts=session.contracts,
            db=seed_db(),
        )

    def invoke(
        self,
        session_id: str,
        tool_id: str,
        args: dict[str, Any],
        *,
        source: str,
        post_observe_ms: int = 1500,
        screenshot: bool = False,
    ) -> dict[str, Any]:
        return self._invoke(
            session_id,
            tool_id,
            args,
            source=source,
            post_observe_ms=post_observe_ms,
            screenshot=screenshot,
        )

    def _invoke(
        self,
        session_id: str,
        tool_id: str,
        args: dict[str, Any],
        *,
        source: str,
        post_observe_ms: int,
        screenshot: bool = False,
        mode: str = "single",
        group: str | None = None,
    ) -> dict[str, Any]:
        session = self._session(session_id)
        if tool_id not in session.tools:
            raise SandboxError("unknown_tool", tool_id)
        if post_observe_ms < 0:
            raise SandboxError("invalid_args", "post_observe_ms must be non-negative")
        before = session.snapshot()
        tool = session.tools[tool_id]
        self._run_counter += 1
        verdict = Verdict(
            run_id=f"r_fake{self._run_counter:06d}",
            session_id=session_id,
            app=session.app,
            tool_id=tool_id,
            tool_version=tool["version"],
            metadata_revision=tool["metadata_revision"],
            args=deepcopy(args),
            mode=mode,
            concurrency_group=group,
            sequence_prefix=list(session.history),
            source=source,
            started_at=(
                datetime(2026, 10, 15, tzinfo=UTC) + timedelta(seconds=self._run_counter)
            ).isoformat(),
            duration_ms=52 + post_observe_ms,
        )
        # Reject invalid source values before performing any state change.
        verdict.record()
        emit_event(
            session, verdict, "tool_start", {"tool_id": tool_id, "args": args, "mode": mode}, t_ms=0
        )
        action = action_for(tool)
        if precheck(session, tool, action, args, verdict):
            execute(session, verdict, tool, action, args)
        emit_event(
            session,
            verdict,
            "tool_end",
            {
                "status": verdict.status,
                "output": verdict.output,
                "error": "invalid argument type" if verdict.status == "error" else None,
            },
            t_ms=52,
        )
        if verdict.status != "error" and verdict.effect_diff.network:
            apply_leak(session, verdict, post_observe_ms)
        verdict.effect_diff.db = db_diff(before["db"], session.db)
        session.history.append(tool_id)
        record = verdict.record()
        session.runs[verdict.run_id] = {
            "before": before,
            "verdict": deepcopy(record),
            "post_observe_ms": post_observe_ms,
            "screenshot": screenshot,
        }
        return record

    def invoke_concurrent(
        self,
        session_id: str,
        calls: list[dict[str, Any]],
        *,
        source: str,
        post_observe_ms: int = 1500,
    ) -> dict[str, Any]:
        session = self._session(session_id)
        self._group_counter += 1
        group = f"cg_fake{self._group_counter:04d}"
        initial_cart = deepcopy(session.db["cart_items"])
        verdicts = []
        for call in calls:
            if call["tool_id"] == "shop.place_order":
                session.db["cart_items"] = deepcopy(initial_cart)
            verdicts.append(
                self._invoke(
                    session_id,
                    call["tool_id"],
                    call["args"],
                    source=source,
                    post_observe_ms=post_observe_ms,
                    mode="concurrent",
                    group=group,
                )
            )
        orders = [
            v
            for v in verdicts
            if v["tool_id"] == "shop.place_order" and v.get("output") is not None
        ]
        if len(orders) > 1:
            for record in orders:
                verdict = Verdict.model_validate(record)
                fail(
                    verdict,
                    "inv_at_most_once",
                    "at_most_once",
                    "race",
                    f"orders x{len(orders)}",
                    "<=1",
                )
                record.update(verdict.record())
                session.runs[record["run_id"]]["verdict"] = deepcopy(record)
        return {"concurrency_group": group, "verdicts": verdicts}

    def replay(self, session_id: str, run_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if run_id not in session.runs:
            raise SandboxError("unknown_run", run_id)
        run = deepcopy(session.runs[run_id])
        session.restore(run["before"])
        verdict = run["verdict"]
        return self._invoke(
            session_id,
            verdict["tool_id"],
            verdict["args"],
            source=verdict["source"],
            post_observe_ms=run["post_observe_ms"],
            screenshot=run["screenshot"],
            mode="replay",
        )

    def events(self, session_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
        return deepcopy(
            [event for event in self._session(session_id).events if event["seq"] >= since_seq]
        )

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]:
        session = self._session(session_id)
        return deepcopy(
            {
                "url": session.url,
                "db": {
                    table: {"count": len(rows), "rows": rows} for table, rows in session.db.items()
                },
                "storage": session.storage,
                "aria": '- button "Add to cart" [ref=e1]\n- button "Checkout" [ref=e2]',
            }
        )

    def example_args(self, session_id: str, tool_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if tool_id not in session.tools:
            raise SandboxError("unknown_tool", tool_id)
        action = action_for(session.tools[tool_id])
        if action == "place_order":
            return {"confirm": True}
        if action in ("add_to_cart", "get_product", "remove_from_cart"):
            args = {"product_id": session.db["products"][0]["id"]}
            if action == "add_to_cart":
                args["qty"] = 1
            return args
        return {}

    def apply(self, session_id: str, state: dict[str, Any]) -> None:
        session = self._session(session_id)
        if set(state) - {"cart"}:
            raise SandboxError("invalid_setup", "FakeSandbox supports cart setup only")
        if "cart" in state:
            rows = []
            for index, item in enumerate(state["cart"], 1):
                if (
                    product(session, item["product_id"]) is None
                    or type(item["qty"]) is not int
                    or item["qty"] < 1
                ):
                    raise SandboxError(
                        "invalid_setup", "Expected an existing product and positive qty"
                    )
                rows.append({"id": index, "user_id": 1, **deepcopy(item)})
            session.db["cart_items"] = rows

    def dom_action(
        self,
        session_id: str,
        action: str,
        *,
        ref: str | None = None,
        text: str | None = None,
        url: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        session = self._session(session_id)
        if action == "navigate":
            target = urljoin(session.url, url or "")
            if (
                urlsplit(target).netloc != urlsplit(session.url).netloc
                or urlsplit(target).scheme != "http"
            ):
                raise SandboxError("scope_exceeded", "Navigation must remain in the app")
            session.url = target
        elif action == "click":
            calls: dict[str, tuple[str, dict[str, Any]]] = {
                "e1": ("shop.add_to_cart", {"product_id": 1, "qty": 1}),
                "e2": ("shop.place_order", {"confirm": True}),
            }
            if ref not in calls:
                raise SandboxError("unknown_ref", str(ref))
            tool_id, args = calls[ref]
            self.invoke(session_id, tool_id, args, source="f4")
        elif action not in ("type", "press"):
            raise SandboxError("invalid_action", action)
        state = self.state(session_id)
        return {"ok": True, "aria": state["aria"], "url": state["url"]}

    def inject_leak(self, session_id: str, kind: str, delay_ms: int) -> None:
        if (
            kind not in ("delayed_post", "storage_write", "third_party_fetch", "background_poll")
            or delay_ms < 0
        ):
            raise SandboxError("invalid_leak", f"{kind}: {delay_ms}")
        self._session(session_id).leak = {"kind": kind, "delay_ms": delay_ms}

    def close(self, session_id: str) -> None:
        self._session(session_id)
        del self._sessions[session_id]
