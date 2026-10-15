"""Check deterministic offline state changes and deliberately emulated safety defects."""

import pytest

from specx.client.fake import FakeSandbox
from specx.client.sandbox import SandboxClient, SandboxError
from specx.client.schemas import validate


@pytest.fixture
def fake():
    return FakeSandbox()


def add(fake, session, **args):
    return fake.invoke(
        session, "shop.add_to_cart", args or {"product_id": 1, "qty": 1}, source="f4"
    )


def test_fake_is_client_and_sessions_are_isolated(fake):
    assert isinstance(fake, SandboxClient)
    first, second = fake.create_session("shop"), fake.create_session("shop")
    verdict = add(fake, first)
    validate("verdict", verdict)
    assert verdict["status"] == "pass"
    assert fake.state(first)["db"]["cart_items"]["count"] == 1
    assert fake.state(second)["db"]["cart_items"]["count"] == 0
    state = fake.state(first)
    state["db"]["products"]["rows"].clear()
    assert fake.state(first)["db"]["products"]["count"] == 5


def test_reset_and_replay_restore_prestate(fake):
    session = fake.create_session("shop", seed=7)
    before = fake.state(session)["db"]
    verdict = add(fake, session)
    replay = fake.replay(session, verdict["run_id"])
    assert replay["mode"] == "replay"
    assert replay["effect_diff"] == verdict["effect_diff"]
    assert replay["clause_results"] == verdict["clause_results"]
    fake.reset(session, seed=7)
    assert fake.state(session)["db"] == before
    assert fake.events(session) == []


def test_concurrent_place_order_exposes_race(fake):
    session = fake.create_session("shop")
    add(fake, session)
    result = fake.invoke_concurrent(
        session, [{"tool_id": "shop.place_order", "args": {"confirm": True}}] * 2, source="s1"
    )
    assert fake.state(session)["db"]["orders"]["count"] == 2
    assert len(result["verdicts"]) == 2
    for verdict in result["verdicts"]:
        validate("verdict", verdict)
        assert verdict["mode"] == "concurrent"
        assert verdict["concurrency_group"] == result["concurrency_group"]
        assert any(v["category"] == "race" for v in verdict["violations"])


@pytest.mark.parametrize(
    ("args", "status", "clause"),
    [
        ({"product_id": 999, "qty": 1}, "fail", "pre_product_exists"),
        ({"product_id": 1, "qty": 999}, "fail", "post_cart_row"),
        ({"product_id": "wrong_type", "qty": 1}, "error", None),
        ({"product_id": 1}, "fail", "pre_required_args"),
    ],
)
def test_invalid_and_boundary_arguments(fake, args, status, clause):
    session = fake.create_session("shop")
    verdict = add(fake, session, **args)
    validate("verdict", verdict)
    assert verdict["status"] == status
    if clause:
        assert any(
            c["clause_id"] == clause and c["passed"] is False for c in verdict["clause_results"]
        )
    else:
        assert verdict["violations"] == []
        assert not any(c["passed"] is False for c in verdict["clause_results"])


def test_one_shot_leak_is_post_phase_and_events_are_valid(fake):
    session = fake.create_session("shop")
    fake.inject_leak(session, "delayed_post", 800)
    verdict = add(fake, session)
    assert any(v["category"] == "unapproved_endpoint" for v in verdict["violations"])
    events = fake.events(session)
    for event in events:
        validate("event_record", event)
    leak = next(e for e in events if e["kind"] == "network_request" and not e["data"]["approved"])
    assert leak["phase"] == "post" and leak["t_ms"] > 800
    assert leak["run_id"] == verdict["run_id"]
    assert fake.events(session, since_seq=leak["seq"])[0] == leak
    assert add(fake, session)["violations"] == []


def test_setup_dom_actions_and_session_lifecycle(fake):
    session = fake.create_session("shop")
    fake.apply(session, {"cart": [{"product_id": 2, "qty": 3}]})
    assert fake.state(session)["db"]["cart_items"]["rows"][0]["qty"] == 3
    assert "[ref=e1]" in fake.state(session)["aria"]
    fake.dom_action(session, "click", ref="e2")
    assert any(
        e["kind"] == "network_request" and e["data"]["url"].endswith("/api/orders")
        for e in fake.events(session)
    )
    with pytest.raises(SandboxError, match="scope_exceeded"):
        fake.dom_action(session, "navigate", url="https://elsewhere.test/")
    fake.close(session)
    assert fake.health()["sessions"] == 0
    with pytest.raises(SandboxError, match="unknown_session"):
        fake.state(session)


def test_same_seed_and_call_order_reproduce_full_records():
    def run():
        with FakeSandbox() as sandbox:
            session = sandbox.create_session("shop", seed=5)
            verdict = add(sandbox, session)
            return verdict, sandbox.events(session)

    assert run() == run()


def test_unknown_app_and_tool_fail_loudly(fake):
    with pytest.raises(SandboxError, match="unknown_app"):
        fake.create_session("other")
    session = fake.create_session("shop")
    with pytest.raises(SandboxError, match="unknown_tool"):
        fake.invoke(session, "shop.missing", {}, source="f4")


def test_example_args_are_read_only_and_valid_for_fixture_tools(fake):
    from jsonschema import Draft202012Validator

    from specx.client.io import read_json
    from specx.client.paths import repo_root

    session = fake.create_session("shop")
    before = fake.state(session)
    for tool in read_json(repo_root() / "fixtures/tools/shop.tools.json"):
        Draft202012Validator(tool["input_schema"]).validate(
            fake.example_args(session, tool["tool_id"])
        )
    assert fake.state(session) == before


def test_loading_revised_tools_keeps_dispatch_on_immutable_id(fake):
    from specx.client.io import read_json
    from specx.client.paths import repo_root

    session = fake.create_session("shop")
    tools = read_json(repo_root() / "fixtures/tools/shop.tools.json")
    tools[1]["name"] = "put_product_in_cart"
    tools[1]["metadata_revision"] = 1
    fake.load_tools(session, tools, [])
    tools[1]["metadata_revision"] = 99
    assert add(fake, session)["metadata_revision"] == 1
    fake.reset(session)
    assert add(fake, session)["metadata_revision"] == 1


@pytest.mark.parametrize(
    ("kind", "category"),
    [
        ("storage_write", "storage"),
        ("third_party_fetch", "third_party"),
        ("background_poll", None),
    ],
)
def test_other_leak_kinds(fake, kind, category):
    session = fake.create_session("shop")
    fake.inject_leak(session, kind, 300)
    verdict = add(fake, session)
    validate("verdict", verdict)
    if category:
        assert any(v["category"] == category for v in verdict["violations"])
    else:
        polls = [n for n in verdict["effect_diff"]["network"] if n["phase"] == "post"]
        assert len(polls) == 5
        assert all(n["approved"] for n in polls)
    assert any(e["phase"] == "post" for e in fake.events(session))


def test_read_does_not_consume_pending_mutation_leak(fake):
    session = fake.create_session("shop")
    fake.inject_leak(session, "delayed_post", 300)
    verdict = fake.invoke(session, "shop.list_products", {}, source="f4")
    assert verdict["violations"] == []
    assert add(fake, session)["violations"]


def test_invalid_source_is_rejected_without_side_effects(fake):
    session = fake.create_session("shop")
    before = fake.state(session)
    with pytest.raises(ValueError, match="verdict/source"):
        fake.invoke(session, "shop.add_to_cart", {"product_id": 1, "qty": 1}, source="invalid")
    assert fake.state(session) == before
    assert fake.events(session) == []


def test_concurrent_orders_with_empty_cart_do_not_create_race(fake):
    session = fake.create_session("shop")
    result = fake.invoke_concurrent(
        session, [{"tool_id": "shop.place_order", "args": {"confirm": True}}] * 2, source="s1"
    )
    assert fake.state(session)["db"]["orders"]["count"] == 0
    assert all(v["status"] == "fail" for v in result["verdicts"])
    assert not any(
        v["category"] == "race" for verdict in result["verdicts"] for v in verdict["violations"]
    )
