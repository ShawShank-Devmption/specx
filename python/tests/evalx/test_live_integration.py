"""Free cross-language checks against real Chromium/apps with no provider calls.

Prerequisites: seed apps + sandbox running, template-generated tools/contracts under
SPECX_RESULTS_DIR (default results). Run with pytest -m sandbox, never -m llm.
"""

import base64
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from specx.client import SandboxClient, SandboxError
from specx.client.io import read_json, write_json, write_jsonl
from specx.client.paths import contracts_path, tools_path
from specx.evalx.agent import run_episode
from specx.evalx.conditions import Condition
from specx.evalx.llm import FakeLLM
from specx.evalx.tasks import Task, check_success, load_tasks
from specx.optim.bundles import harvest
from specx.optim.images import decode_png

pytestmark = pytest.mark.sandbox


@pytest.fixture
def live() -> Iterator[SandboxClient]:
    with SandboxClient() as client:
        assert {"shop", "admin"} <= set(client.health()["apps"])
        yield client


def toolset(app: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return read_json(tools_path(app)), read_json(contracts_path(app))


def call(
    client: SandboxClient,
    sid: str,
    tools: list[dict[str, Any]],
    method: str,
    path: str,
    **args: Any,
) -> dict[str, Any]:
    tool = next(
        tool
        for tool in tools
        if tool["handler"].get("http") == {"method": method, "path_template": path}
    )
    verdict = client.invoke(sid, tool["tool_id"], args, source="fixture", post_observe_ms=0)
    assert verdict["status"] != "error", verdict
    return verdict


@pytest.mark.parametrize("app", ["shop", "admin"])
def test_real_reset_isolation_setup_and_png(live: SandboxClient, app: str) -> None:
    first, second = live.create_session(app, seed=0), live.create_session(app, seed=0)
    try:
        before = live.state(first)["db"]
        if app == "admin":
            users = before["users"]["rows"]
            assert [(u["id"], u["username"], u["role"], u["active"]) for u in users] == [
                (1, "root", "admin", 1),
                (2, "bob", "editor", 1),
                (3, "carol", "viewer", 1),
                (4, "erin", "viewer", 1),
                (5, "hank", "editor", 1),
                (6, "ivy", "viewer", 1),
            ]
            live.apply(
                first,
                {
                    "users": [
                        {
                            "username": "dana",
                            "email": "dana@example.com",
                            "role": "viewer",
                            "active": 1,
                        }
                    ]
                },
            )
            assert live.state(first)["db"]["users"]["count"] == 7
            assert live.state(second)["db"]["users"]["count"] == 6
        else:
            live.apply(first, {"cart": [{"product_id": 3, "qty": 1}]})
            assert live.state(first)["db"]["cart_items"]["count"] == 1
            assert live.state(second)["db"]["cart_items"]["count"] == 0
        live.reset(first, seed=0)
        assert live.state(first)["db"] == before
        encoded = live.state(first, screenshot=True)["screenshot_b64"]
        assert base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        live.close(first)
        live.close(second)


def test_real_client_replay_events_and_errors(live: SandboxClient) -> None:
    tools, contracts = toolset("shop")
    sid = live.create_session("shop", seed=0)
    try:
        live.load_tools(sid, tools, contracts)
        original = call(live, sid, tools, "POST", "/api/cart", product_id=2, qty=1)
        replay = live.replay(sid, original["run_id"])
        assert replay["effect_diff"]["db"] == original["effect_diff"]["db"]
        assert [(c["clause_id"], c["passed"]) for c in replay["clause_results"]] == [
            (c["clause_id"], c["passed"]) for c in original["clause_results"]
        ]
        events = live.events(sid)
        assert any(e["kind"] == "network_request" for e in events)
        assert live.events(sid, since_seq=max(e["seq"] for e in events) + 1) == []
        assert live.example_args(sid, "shop.add_to_cart")["product_id"] in range(1, 6)
        with pytest.raises(SandboxError) as error:
            live.invoke(sid, "shop.missing", {}, source="fixture", post_observe_ms=0)
        assert error.value.code == "unknown_tool"
    finally:
        live.close(sid)


def complete_task(task: Task, client: SandboxClient, sid: str, tools: list[dict[str, Any]]) -> None:
    def invoke(method: str, path: str, **args: Any) -> None:
        call(client, sid, tools, method, path, **args)

    number = int(task.task_id.rsplit("t", 1)[1])
    if task.app == "shop":
        if number in (3, 8):
            products = [3] if number == 3 else [1, 2]
            for product in products:
                invoke("DELETE", "/api/cart/{product_id}", product_id=product)
            return
        products_and_qty = {
            1: [(1, 2)],
            2: [(2, 1)],
            4: [(4, 3)],
            5: [(5, 1)],
            6: [(1, 1), (2, 1)],
            7: [(5, 1)],
            9: [(3, 1)],
            10: [(3, 1), (4, 1)],
        }
        if number == 5:
            invoke("GET", "/api/orders")
        for product, qty in products_and_qty[number]:
            invoke("POST", "/api/cart", product_id=product, qty=qty)
        if number in (1, 7):
            invoke("POST", "/api/orders", confirm=True)
        return
    if number in (1, 2, 6):
        username, role = {1: ("gina", "editor"), 2: ("dana", "viewer"), 6: ("frank", "viewer")}[
            number
        ]
        if number == 6:
            invoke("GET", "/api/users")
        invoke("POST", "/api/users", username=username, email=f"{username}@example.com", role=role)
    elif number == 3:
        invoke("PATCH", "/api/users/{id}", id=2, email="bob.updated@example.com")
    elif number in (4, 7):
        invoke("POST", "/api/users/{id}/deactivate", id=3 if number == 4 else 2)
    elif number == 5:
        invoke("POST", "/api/users/{id}/role", id=4, role="editor")
    elif number == 8:
        invoke("DELETE", "/api/users/{id}", id=3)
    elif number == 9:
        invoke("PATCH", "/api/users/{id}", id=4, username="erin2")
    else:
        dana = next(u for u in client.state(sid)["db"]["users"]["rows"] if u["username"] == "dana")
        invoke("POST", "/api/users/{id}/deactivate", id=2)
        invoke("POST", "/api/users/{id}/role", id=dana["id"], role="admin")


@pytest.mark.parametrize(
    "task",
    [task for app in ("shop", "admin") for task in load_tasks(app)],
    ids=lambda task: task.task_id,
)
def test_all_twenty_task_checks_on_fresh_real_state(live: SandboxClient, task: Task) -> None:
    tools, contracts = toolset(task.app)
    sid = live.create_session(task.app, seed=0)
    try:
        live.load_tools(sid, tools, contracts)
        live.reset(sid, seed=0)
        if task.setup:
            live.apply(sid, task.setup)
        assert not check_success(task, live, sid)
        complete_task(task, live, sid, tools)
        assert check_success(task, live, sid)
    finally:
        live.close(sid)


def response(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_reason": "tool_use",
        "usage": {},
        "content": [{"type": "tool_use", "id": name, "name": name, "input": args}],
    }


@pytest.mark.parametrize(
    "app,task_id,method,path,args",
    [
        ("shop", "shop.t02", "POST", "/api/cart", {"product_id": 2, "qty": 1}),
        (
            "admin",
            "admin.t02",
            "POST",
            "/api/users",
            {"username": "dana", "email": "dana@example.com", "role": "viewer"},
        ),
    ],
)
def test_scripted_frozen_agent_on_real_apps(
    live: SandboxClient, app: str, task_id: str, method: str, path: str, args: dict[str, Any]
) -> None:
    tools, contracts = toolset(app)
    tool = next(
        t for t in tools if t["handler"].get("http") == {"method": method, "path_template": path}
    )
    model = FakeLLM(
        [response(tool["name"], args), response("finish", {"summary": "Done"})],
        model="scripted-integration-no-provider",
    )
    trial, trace = run_episode(
        live,
        app,
        next(t for t in load_tasks(app) if t.task_id == task_id),
        Condition.generated,
        0,
        tools=tools,
        contracts=contracts,
        llm=model,
        max_steps=5,
    )
    assert trial["success"] and not trial["policy_violations"]
    assert trace["verdicts"] and trace["final_screenshot_b64"]


def test_raw_dom_policy_uses_real_events(live: SandboxClient, tmp_path: Path) -> None:
    class RawScript(FakeLLM):
        def create(self, **kwargs: Any) -> dict[str, Any]:
            if not self.calls:
                answer = response("navigate", {"path": "/cart"})
            elif len(self.calls) == 1:
                result = kwargs["messages"][-1]["content"][0]["content"]
                text = json.loads(result)["aria"]
                match = re.search(r'button "Place order" \[ref=(e\d+)\]', text)
                assert match, text
                answer = response("click", {"ref": match[1]})
            else:
                answer = response("finish", {"summary": "Done"})
            self._responses.append(answer)
            return super().create(**kwargs)

    task = next(t for t in load_tasks("shop") if t.task_id == "shop.t08")
    trial, trace = run_episode(
        live,
        "shop",
        task,
        Condition.raw_dom,
        0,
        tools=[],
        llm=RawScript([], model="scripted-integration-no-provider"),
        max_steps=5,
    )
    assert trial["success"]  # The order empties the cart, but violates the separate policy.
    assert any(v["kind"] == "unconfirmed_destructive" for v in trial["policy_violations"])
    assert not trace["verdicts"] and any(e["kind"] == "network_request" for e in trace["events"])
    # Exercise C6 on genuine browser evidence without polluting benchmark cohorts.
    write_json(tmp_path / f"{trial['trial_id']}.json", trace)
    trials = tmp_path / "scripted.jsonl"
    write_jsonl(trials, [trial])
    bundles = harvest(trials, tmp_path, [])
    assert len(bundles) == 1 and bundles[0].failure_reason == "policy_violation"
    assert bundles[0].network_log and bundles[0].dom_diff
    assert not bundles[0].synthetic and not bundles[0].tool_ids
    assert bundles[0].screenshot_b64 is not None
    assert decode_png(bundles[0].screenshot_b64).startswith(b"\x89PNG")
    assert harvest(trials, tmp_path, [], split="train") == []
