"""Verify the HTTP boundary without starting a sandbox or accessing the network."""

import json

import httpx
import pytest
import respx

from specx.client.io import read_json, read_jsonl
from specx.client.paths import repo_root
from specx.client.sandbox import SandboxClient, SandboxError

BASE = "http://sandbox.test"


@pytest.fixture
def client():
    with SandboxClient(BASE) as sandbox:
        yield sandbox


@respx.mock
def test_invoke_posts_body_and_strips_transport_version(client):
    verdict = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[0]
    route = respx.post(f"{BASE}/sessions/s1/invoke").mock(
        return_value=httpx.Response(200, json={**verdict, "api_version": "1"})
    )
    assert (
        client.invoke(
            "s1",
            "shop.add_to_cart",
            {"product_id": 1, "qty": 1},
            source="f4",
            post_observe_ms=300,
            screenshot=True,
        )
        == verdict
    )
    assert json.loads(route.calls.last.request.content) == {
        "tool_id": "shop.add_to_cart",
        "args": {"product_id": 1, "qty": 1},
        "source": "f4",
        "post_observe_ms": 300,
        "screenshot": True,
    }


@respx.mock
@pytest.mark.parametrize("status", [200, 400, 404, 500])
def test_error_envelopes_raise_sandbox_error(client, status):
    respx.post(f"{BASE}/sessions/s1/invoke").respond(
        status, json={"error": {"code": "unknown_tool", "message": "Missing tool"}}
    )
    with pytest.raises(SandboxError) as error:
        client.invoke("s1", "missing", {}, source="f4")
    assert error.value.code == "unknown_tool"
    assert error.value.message == "Missing tool"


@respx.mock
def test_invalid_verdict_is_rejected(client):
    respx.post(f"{BASE}/sessions/s1/invoke").respond(200, json={"status": "pass"})
    with pytest.raises(ValueError, match="verdict/"):
        client.invoke("s1", "shop.add_to_cart", {}, source="f4")


@respx.mock
def test_lifecycle_and_setup_requests(client):
    health = respx.get(f"{BASE}/health").respond(200, json={"ok": True})
    create = respx.post(f"{BASE}/sessions").respond(200, json={"session_id": "s1"})
    reset = respx.post(f"{BASE}/sessions/s1/reset").respond(200, json={"ok": True})
    load = respx.put(f"{BASE}/sessions/s1/tools").respond(200, json={"ok": True})
    apply = respx.post(f"{BASE}/sessions/s1/apply").respond(200, json={"ok": True})
    leak = respx.post(f"{BASE}/sessions/s1/inject_leak").respond(200, json={"ok": True})
    close = respx.delete(f"{BASE}/sessions/s1").respond(200, json={"ok": True})
    assert client.health() == {"ok": True}
    assert (
        client.create_session("shop", seed=3, leak={"kind": "delayed_post", "delay_ms": 800})
        == "s1"
    )
    assert json.loads(create.calls.last.request.content)["seed"] == 3
    client.reset("s1", seed=4)
    assert json.loads(reset.calls.last.request.content) == {"seed": 4}
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    contracts = read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    client.load_tools("s1", tools, contracts)
    assert json.loads(load.calls.last.request.content) == {"tools": tools, "contracts": contracts}
    client.apply("s1", {"cart": [{"product_id": 1, "qty": 2}]})
    assert json.loads(apply.calls.last.request.content) == {
        "state": {"cart": [{"product_id": 1, "qty": 2}]}
    }
    client.inject_leak("s1", "delayed_post", 800)
    assert json.loads(leak.calls.last.request.content) == {"kind": "delayed_post", "delay_ms": 800}
    client.close("s1")
    assert health.called and close.called


@respx.mock
def test_reads_dom_actions_concurrent_and_replay(client):
    event = read_jsonl(repo_root() / "fixtures/events/approved_trace.jsonl")[0]
    respx.get(f"{BASE}/sessions/s1/events").respond(200, json={"events": [event]})
    assert client.events("s1", since_seq=3) == [event]
    assert respx.calls.last.request.url.params["since_seq"] == "3"
    respx.get(f"{BASE}/sessions/s1/state").respond(200, json={"db": {}, "aria": "hello"})
    assert client.state("s1", screenshot=True)["aria"] == "hello"
    assert respx.calls.last.request.url.params["screenshot"] == "true"
    respx.get(f"{BASE}/sessions/s1/example_args").respond(200, json={"args": {"qty": 1}})
    assert client.example_args("s1", "shop.add_to_cart") == {"qty": 1}
    respx.post(f"{BASE}/sessions/s1/dom_action").respond(200, json={"ok": True, "aria": "cart"})
    assert client.dom_action("s1", "click", ref="e1")["ok"]
    assert json.loads(respx.calls.last.request.content) == {"action": "click", "ref": "e1"}
    verdict = read_jsonl(repo_root() / "fixtures/verdicts/sample.verdicts.jsonl")[2]
    calls = [{"tool_id": "shop.place_order", "args": {"confirm": True}}] * 2
    respx.post(f"{BASE}/sessions/s1/invoke_concurrent").respond(
        200, json={"concurrency_group": "cg1", "verdicts": [verdict]}
    )
    assert client.invoke_concurrent("s1", calls, source="s1")["verdicts"] == [verdict]
    assert json.loads(respx.calls.last.request.content)["calls"] == calls
    respx.post(f"{BASE}/sessions/s1/replay").respond(200, json=verdict)
    assert client.replay("s1", "r1") == verdict


@respx.mock
def test_environment_base_url_and_transport_errors(monkeypatch):
    monkeypatch.setenv("SPECX_SANDBOX_URL", BASE)
    respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("offline"))
    with SandboxClient() as sandbox, pytest.raises(SandboxError, match="offline"):
        sandbox.health()


@respx.mock
@pytest.mark.parametrize("body", [{"verdicts": [{"status": "pass"}]}, {"verdicts": [None]}])
def test_concurrent_validates_each_verdict(client, body):
    respx.post(f"{BASE}/sessions/s1/invoke_concurrent").respond(200, json=body)
    with pytest.raises((ValueError, SandboxError)):
        client.invoke_concurrent("s1", [], source="s1")


@respx.mock
def test_invalid_event_is_rejected(client):
    respx.get(f"{BASE}/sessions/s1/events").respond(200, json={"events": [{}]})
    with pytest.raises(ValueError, match="event_record/"):
        client.events("s1")


@respx.mock
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(200, text="not json"), "invalid_response"),
        (httpx.Response(200, json=[]), "invalid_response"),
        (httpx.Response(503, json={}), "http_503"),
        (httpx.Response(200, json={"api_version": "2", "ok": True}), "api_version"),
    ],
)
def test_malformed_responses_and_unsupported_versions(client, response, code):
    respx.get(f"{BASE}/health").mock(return_value=response)
    with pytest.raises(SandboxError) as error:
        client.health()
    assert error.value.code == code


@respx.mock
def test_invalid_outgoing_tools_do_not_reach_network(client):
    route = respx.put(f"{BASE}/sessions/s1/tools").respond(200, json={"ok": True})
    with pytest.raises(ValueError, match="tool_definition/"):
        client.load_tools("s1", [{"tool_id": "shop.invalid"}], [])
    assert not route.called
