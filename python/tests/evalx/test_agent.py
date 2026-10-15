"""Exercise the frozen harness with scripted responses and the offline sandbox."""

from typing import Any

import pytest

from specx.client import FakeSandbox
from specx.client.io import read_json
from specx.client.paths import repo_root
from specx.client.schemas import validate
from specx.evalx.agent import run_episode
from specx.evalx.conditions import Condition
from specx.evalx.llm import FakeLLM
from specx.evalx.tasks import load_tasks


def use(name: str, args: Any, call_id: str = "call1") -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def response(*content: dict[str, Any], stop: str = "tool_use", **usage: int) -> dict[str, Any]:
    return {
        "stop_reason": stop,
        "content": list(content),
        "usage": {"input_tokens": 10, "output_tokens": 2, **usage},
    }


@pytest.fixture(autouse=True)
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("SPECX_AGENT_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path))


def episode(
    script: list[dict[str, Any]],
    *,
    condition: Condition = Condition.generated,
    task_id: str = "shop.t02",
    max_steps: int = 10,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], FakeLLM]:
    tools = (
        tools if tools is not None else read_json(repo_root() / "fixtures/tools/shop.tools.json")
    )
    contracts = read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    task = next(t for t in load_tasks("shop") if t.task_id == task_id)
    llm = FakeLLM(script)
    with FakeSandbox() as client:
        trial, trace = run_episode(
            client,
            "shop",
            task,
            condition,
            3,
            tools=tools,
            contracts=contracts,
            llm=llm,
            max_steps=max_steps,
        )
        assert client.health()["sessions"] == 0
    return trial, trace, llm


def test_scripted_add_to_cart_produces_valid_trial_and_trace() -> None:
    trial, trace, llm = episode(
        [
            response(use("add_to_cart", {"product_id": 2, "qty": 1})),
            response(use("finish", {"summary": "Done"})),
        ]
    )
    validate("trial_result", trial)
    assert trial["success"] and trial["failure_reason"] == "none"
    assert trial["steps"] == 2 and trial["seed"] == 3
    assert trial["input_tokens"] == 20 and trial["output_tokens"] == 4
    assert trace["verdicts"][0]["source"] == "f4"
    assert trace["task_id"] == "shop.t02" and "final_screenshot_b64" in trace
    assert trace["aria_before"] and trace["aria_after"]
    first_call = llm.calls[0]
    assert first_call["output_config"] == {"effort": "medium"}
    assert first_call["model"] == trial["agent_model"]
    assert first_call["max_tokens"] == 4096
    assert "cache_control" in first_call["system"][0]
    assert "cache_control" in first_call["tools"][-1]
    assert all(tool["strict"] for tool in first_call["tools"])
    assert not {"temperature", "thinking", "tool_choice"} & first_call.keys()


def test_tool_results_single_message_and_full_assistant_content() -> None:
    content = [
        {"type": "thinking", "thinking": "Plan", "signature": "signed"},
        {"type": "text", "text": "I will add both."},
        use("add_to_cart", {"product_id": 1, "qty": 1}, "a"),
        use("add_to_cart", {"product_id": 2, "qty": 1}, "b"),
    ]
    trial, trace, llm = episode(
        [response(*content), response(use("finish", {"summary": "Done"}))], task_id="shop.t06"
    )
    assert trial["success"]
    messages = llm.calls[1]["messages"]
    assert messages[-2] == {"role": "assistant", "content": content}
    assert messages[-1]["role"] == "user"
    assert [block["tool_use_id"] for block in messages[-1]["content"]] == ["a", "b"]
    assert all(block["type"] == "tool_result" for block in messages[-1]["content"])
    assert len(trace["verdicts"]) == 2


def test_raw_dom_policy_from_network() -> None:
    trial, trace, llm = episode(
        [
            response(use("click", {"ref": "e2"})),
            response(use("finish", {"summary": "Finished"})),
        ],
        condition=Condition.raw_dom,
        task_id="shop.t08",
    )
    assert trial["tool_set_version"] == "none"
    assert any(v["kind"] == "unconfirmed_destructive" for v in trial["policy_violations"])
    assert any(
        e["kind"] == "network_request" and e["data"]["url"].endswith("/api/orders")
        for e in trace["events"]
    )
    assert {tool["name"] for tool in llm.calls[0]["tools"]} == {
        "observe",
        "click",
        "type",
        "navigate",
        "finish",
    }
    assert trace["verdicts"] == []  # detection does not depend on tool-mode verdicts


def test_token_accounting_preserves_cache_fields_in_trace() -> None:
    trial, trace, _ = episode(
        [
            response(
                use("observe", {}), input_tokens=7, output_tokens=3, cache_read_input_tokens=100
            ),
            response(
                use("finish", {"summary": "Cannot do it"}),
                input_tokens=11,
                output_tokens=4,
                cache_creation_input_tokens=50,
            ),
        ]
    )
    assert trial["input_tokens"] == 18 and trial["output_tokens"] == 7
    assert trace["usage"]["cache_read_input_tokens"] == 100
    assert trace["usage"]["cache_creation_input_tokens"] == 50


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        ([response(use("finish", {"summary": "Impossible"}))], "gave_up"),
        ([response({"type": "text", "text": "Done"}, stop="end_turn")], "wrong_tool"),
        ([response(stop="refusal")], "policy_stop"),
        ([response(use("add_to_cart", {"product_id": 2, "qty": 1}), stop="max_tokens")], "gave_up"),
        (
            [
                response(use("add_to_cart", {"product_id": "wrong_type", "qty": 1})),
                response(use("finish", {"summary": "Failed"})),
            ],
            "handler_error",
        ),
        (
            [
                response(use("add_to_cart", {"product_id": 999, "qty": 1})),
                response(use("finish", {"summary": "Failed"})),
            ],
            "bad_args",
        ),
    ],
)
def test_failure_reasons_and_non_executable_stop_reasons(
    script: list[dict[str, Any]], reason: str
) -> None:
    trial, trace, _ = episode(script)
    assert not trial["success"] and trial["failure_reason"] == reason
    validate("trial_result", trial)
    if trace["stop_reason"] in ("max_tokens", "refusal"):
        assert trace["verdicts"] == []


def test_max_steps_stops_without_an_extra_model_request() -> None:
    trial, _, llm = episode([response(use("observe", {}))], max_steps=1)
    assert trial["steps"] == len(llm.calls) == 1
    assert trial["failure_reason"] == "max_steps"


def test_finish_does_not_skip_sibling_tool_calls() -> None:
    trial, trace, _ = episode(
        [
            response(
                use("finish", {"summary": "Done"}, "a"),
                use("add_to_cart", {"product_id": 2, "qty": 1}, "b"),
            )
        ]
    )
    assert trial["success"] and len(trace["verdicts"]) == 1
    assert len(trace["messages"][-1]["content"]) == 2


def test_malformed_json_input_is_returned_as_a_tool_error() -> None:
    trial, trace, _ = episode(
        [response(use("add_to_cart", "not-json")), response(use("finish", {"summary": "Failed"}))]
    )
    assert trial["failure_reason"] == "bad_args"
    assert trace["messages"][2]["content"][0]["is_error"]


def test_json_encoded_input_is_parsed() -> None:
    trial, _, _ = episode(
        [
            response(use("add_to_cart", '{"product_id":2,"qty":1}')),
            response(use("finish", {"summary": "Done"})),
        ]
    )
    assert trial["success"]


def test_generated_quarantine_is_counted_but_verified_tools_are_filtered() -> None:
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[1]["status"] = "quarantined"
    script = [
        response(use("add_to_cart", {"product_id": 2, "qty": 1})),
        response(use("finish", {"summary": "Done"})),
    ]
    generated, _, _ = episode(script, tools=tools)
    assert generated["quarantined_tool_calls"] == 1
    assert any(v["kind"] == "quarantined_tool" for v in generated["policy_violations"])
    verified, _, llm = episode(script, tools=tools, condition=Condition.verified)
    assert not verified["success"] and verified["quarantined_tool_calls"] == 0
    assert "add_to_cart" not in {tool["name"] for tool in llm.calls[0]["tools"]}


def test_caller_owned_session_is_reset_and_kept_open() -> None:
    task = next(t for t in load_tasks("shop") if t.task_id == "shop.t08")
    with FakeSandbox() as client:
        session = client.create_session("shop")
        client.invoke(session, "shop.add_to_cart", {"product_id": 3, "qty": 1}, source="f4")
        trial, _ = run_episode(
            client,
            "shop",
            task,
            Condition.raw_dom,
            4,
            session_id=session,
            tools=[],
            llm=FakeLLM([response(use("finish", {"summary": "Cannot"}))]),
            max_steps=1,
        )
        assert not trial["success"]
        assert client.health()["sessions"] == 1
        assert client.state(session)["db"]["cart_items"]["count"] == 2


def test_owned_session_is_closed_when_model_raises() -> None:
    with FakeSandbox() as client, pytest.raises(RuntimeError, match="exhausted"):
        try:
            run_episode(
                client,
                "shop",
                load_tasks("shop")[0],
                Condition.raw_dom,
                0,
                tools=[],
                llm=FakeLLM([]),
                max_steps=1,
            )
        finally:
            assert client.health()["sessions"] == 0


@pytest.mark.parametrize("condition", [Condition.generated, Condition.raw_dom])
def test_unapproved_calls_count_leaks_in_tool_and_raw_modes(condition: Condition) -> None:
    class LeakySandbox(FakeSandbox):
        def invoke(
            self, session_id: str, tool_id: str, args: dict[str, Any], **kwargs: Any
        ) -> dict[str, Any]:
            self.inject_leak(session_id, "delayed_post", 300)
            return super().invoke(session_id, tool_id, args, **kwargs)

    calls = (
        [response(use("click", {"ref": "e1"}))]
        if condition == Condition.raw_dom
        else [response(use("add_to_cart", {"product_id": 2, "qty": 1}))]
    )
    calls.append(response(use("finish", {"summary": "Done"})))
    with LeakySandbox() as client:
        result, _ = run_episode(
            client,
            "shop",
            load_tasks("shop")[1],
            condition,
            0,
            tools=read_json(repo_root() / "fixtures/tools/shop.tools.json"),
            contracts=read_json(repo_root() / "fixtures/contracts/shop.contracts.json"),
            llm=FakeLLM(calls),
            max_steps=2,
        )
    assert result["unapproved_calls"] == 1
    assert any(v["kind"] == "unapproved_endpoint" for v in result["policy_violations"])


def test_rejected_outside_navigation_is_still_a_policy_violation() -> None:
    trial, trace, _ = episode(
        [
            response(use("navigate", {"path": "https://elsewhere.test/"})),
            response(use("finish", {"summary": "Blocked"})),
        ],
        condition=Condition.raw_dom,
    )
    assert any(v["kind"] == "scope_exceeded" for v in trial["policy_violations"])
    assert trace["step_log"][0]["error_code"] == "scope_exceeded"


def test_observe_and_initial_prompt_do_not_expose_database_state() -> None:
    _, trace, llm = episode(
        [response(use("observe", {})), response(use("finish", {"summary": "Done"}))]
    )
    assert "cart_items" not in llm.calls[0]["messages"][0]["content"][0]["text"]
    assert '"db"' not in trace["messages"][2]["content"][0]["content"]
    assert trace["system"] == llm.calls[0]["system"]
    assert trace["tools"] == llm.calls[0]["tools"]
