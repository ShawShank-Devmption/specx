"""Exercise resumable persistence and pooled runner sessions without live services."""

from pathlib import Path
from threading import Barrier, Lock, get_ident
from typing import Any
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from specx.client import FakeSandbox, SandboxClient
from specx.client.io import read_json, read_jsonl, write_json
from specx.client.paths import contracts_path, repo_root, tools_path, traces_dir, trials_path
from specx.evalx.benchmark_store import TrialStore
from specx.evalx.conditions import Condition
from specx.evalx.llm import AgentLLM, AnthropicLLM, FakeLLM
from specx.evalx.run import _jobs, app, run_benchmark


def script() -> list[dict[str, Any]]:
    return [
        {
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "content": [{"type": "tool_use", "id": "call", "name": name, "input": args}],
        }
        for name, args in [
            ("add_to_cart", {"product_id": 2, "qty": 1}),
            ("finish", {"summary": "Done"}),
        ]
    ]


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SPECX_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("SPECX_AGENT_MODEL", "claude-sonnet-5-5")
    write_json(tools_path("shop"), read_json(repo_root() / "fixtures/tools/shop.tools.json"))
    write_json(
        contracts_path("shop"), read_json(repo_root() / "fixtures/contracts/shop.contracts.json")
    )
    return tmp_path / "metadata"


def run(
    out: Path,
    llm: AgentLLM,
    *,
    trials: int = 1,
    workers: int = 1,
    condition: Condition = Condition.generated,
    factory: Any = FakeSandbox,
) -> dict[str, Any]:
    return run_benchmark(
        apps=["shop"],
        conditions=[condition],
        trials=trials,
        seed=0,
        split="train",
        task_ids=["shop.t02"],
        workers=workers,
        out=out,
        llm=llm,
        client_factory=factory,
    )


def test_runner_persists_valid_trial_trace_metrics_and_run_metadata(configured: Path) -> None:
    metrics = run(configured, FakeLLM(script()))
    rows = read_jsonl(trials_path("generated"))
    assert len(rows) == 1 and rows[0]["success"]
    trace_path = Path(rows[0]["trace_path"])
    trace = read_json(trace_path)
    assert trace["messages"] and trace["step_log"] and trace["verdicts"]
    assert "final_screenshot_b64" in trace and trace["task"]["task_id"] == "shop.t02"
    assert trace["run_context"]["agent_model"] == rows[0]["agent_model"]
    assert metrics["conditions"]["generated"]["shop"]["n"] == 1
    metadata = read_json(configured / "run.json")
    assert metadata["status"] == "complete" and metadata["completed"] == 1
    assert metadata["git_sha"] and metadata["models"]["agent"] == "claude-sonnet-5-5"
    assert read_json(configured / "metrics.json") == metrics


def test_resume_skips_completed_trials_without_calling_model(configured: Path) -> None:
    run(configured, FakeLLM(script()))
    llm = FakeLLM([])
    run(configured, llm)
    assert llm.calls == [] and len(read_jsonl(trials_path("generated"))) == 1
    metadata = read_json(configured / "run.json")
    assert metadata["skipped"] == 1 and metadata["completed"] == 0


def test_resume_refuses_model_or_trace_context_changes(configured: Path) -> None:
    run(configured, FakeLLM(script()))
    with pytest.raises(ValueError, match=r"model|context"):
        run(configured, FakeLLM([], model="different-model"))
    rows = read_jsonl(trials_path("generated"))
    trace_path = Path(rows[0]["trace_path"])
    trace = read_json(trace_path)
    trace["run_context"]["task_hash"] = "changed"
    write_json(trace_path, trace)
    with pytest.raises(ValueError, match="context"):
        run(configured, FakeLLM([]))


def test_orphan_trace_is_replaced_but_missing_completed_trace_is_rejected(configured: Path) -> None:
    orphan = traces_dir() / "shop.t02.generated.s0.json"
    write_json(orphan, {"orphan": True})
    run(configured, FakeLLM(script()))
    assert "orphan" not in read_json(orphan)
    orphan.unlink()
    with pytest.raises(ValueError, match="trace"):
        run(configured, FakeLLM([]))


def test_sessions_are_reused_and_closed(configured: Path) -> None:
    clients: list[FakeSandbox] = []

    def factory() -> FakeSandbox:
        instance = FakeSandbox()
        clients.append(instance)
        return instance

    metrics = run(configured, FakeLLM(script() * 3), trials=3, factory=factory)
    assert metrics["conditions"]["generated"]["shop"]["n"] == 3
    assert all(client.health()["sessions"] == 0 for client in clients)
    rows = read_jsonl(trials_path("generated"))
    assert len({read_json(Path(row["trace_path"]))["session_id"] for row in rows}) == 1
    assert {row["seed"] for row in rows} == {0, 1, 2}


def test_failure_persists_prior_success_and_can_resume(configured: Path) -> None:
    with pytest.raises(RuntimeError, match="exhausted"):
        run(configured, FakeLLM(script()), trials=2)
    assert len(read_jsonl(trials_path("generated"))) == 1
    assert read_json(configured / "run.json")["status"] == "failed"
    run(configured, FakeLLM(script()), trials=2)
    assert len(read_jsonl(trials_path("generated"))) == 2


def test_raw_dom_has_no_tool_or_contract_file_dependency(configured: Path) -> None:
    tools_path("shop").unlink()
    contracts_path("shop").unlink()
    llm = FakeLLM(
        [
            {
                "stop_reason": "tool_use",
                "usage": {},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "f",
                        "name": "finish",
                        "input": {"summary": "Cannot"},
                    }
                ],
            }
        ]
    )
    run(configured, llm, condition=Condition.raw_dom)
    assert read_jsonl(trials_path("raw_dom"))[0]["tool_set_version"] == "none"


def test_cli_help_and_invalid_options() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["--trials", "0"])
    assert result.exit_code != 0 and "trials" in result.output


def test_default_heldout_design_has_fifty_paired_seeded_jobs() -> None:
    first = _jobs(["shop", "admin"], [Condition.raw_dom], 5, 0, "heldout", None, None)
    second = _jobs(["admin", "shop"], [Condition.raw_dom], 5, 0, "heldout", None, None)
    assert len(first) == 50
    assert [job.trial_id for job in first] == [job.trial_id for job in second]
    for name in ("shop", "admin"):
        assert len([job for job in first if job.task.app == name]) == 25
    assert {job.seed for job in first} == set(range(5))


def test_eight_parallel_workers_reuse_sessions_and_serialize_output(configured: Path) -> None:
    barrier, lock = Barrier(8), Lock()
    threads: set[int] = set()
    counts = {"live": 0, "peak": 0, "created": 0}

    class TrackingSandbox(FakeSandbox):
        def create_session(self, *args: Any, **kwargs: Any) -> str:
            sid = super().create_session(*args, **kwargs)
            with lock:
                counts["live"] += 1
                counts["peak"] = max(counts["peak"], counts["live"])
                counts["created"] += 1
            return sid

        def close(self, session_id: str) -> None:
            super().close(session_id)
            with lock:
                counts["live"] -= 1

    class FinishLLM:
        model = "claude-sonnet-5-5"

        def create(self, **kwargs: Any) -> dict[str, Any]:
            with lock:
                first = get_ident() not in threads
                threads.add(get_ident())
            if first:
                barrier.wait(timeout=10)
            return FakeLLM(
                [
                    {
                        "stop_reason": "tool_use",
                        "usage": {},
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "f",
                                "name": "finish",
                                "input": {"summary": "Cannot"},
                            }
                        ],
                    }
                ]
            ).create(**kwargs)

        def episode_finished(self) -> None:
            pass

    metrics = run_benchmark(
        apps=["shop"],
        conditions=[Condition.raw_dom],
        trials=16,
        seed=0,
        split="train",
        task_ids=["shop.t02"],
        workers=8,
        out=configured,
        llm=FinishLLM(),
        client_factory=TrackingSandbox,
    )
    assert counts == {"live": 0, "peak": 8, "created": 8}
    assert len(threads) == 8 and metrics["completed"] == 16
    rows = read_jsonl(trials_path("raw_dom"))
    assert len(rows) == len({row["trial_id"] for row in rows}) == 16


def test_concurrent_runner_is_rejected_before_writing(configured: Path) -> None:
    with TrialStore().writer(), pytest.raises(RuntimeError, match="Another benchmark"):
        run(configured, FakeLLM(script()))


def test_resume_refuses_changed_contracts(configured: Path) -> None:
    run(configured, FakeLLM(script()))
    contracts = read_json(contracts_path("shop"))
    contracts[0]["preconditions"][0]["description"] = "Updated contract"
    write_json(contracts_path("shop"), contracts)
    with pytest.raises(ValueError, match="context"):
        run(configured, FakeLLM([]))


def test_resume_preserves_shared_estimated_spend_and_episode_count(configured: Path) -> None:
    provider = Mock()
    provider.messages.create.return_value.model_dump.return_value = {
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "content": [
            {"type": "tool_use", "id": "f", "name": "finish", "input": {"summary": "Cannot"}}
        ],
    }
    first = AnthropicLLM(sdk=provider)
    run(configured, first, condition=Condition.raw_dom)
    resumed = AnthropicLLM(sdk=provider)
    run(configured, resumed, condition=Condition.raw_dom, trials=2)
    assert resumed.spent_usd == pytest.approx(first.spent_usd * 2)
    assert resumed.episodes == 2


@pytest.mark.sandbox
def test_real_sandbox_one_episode_with_fake_llm(configured: Path) -> None:
    metrics = run(configured, FakeLLM(script()), factory=SandboxClient)
    assert metrics["conditions"]["generated"]["shop"]["success_rate"] == 1
