"""Verify SDK request forwarding, response normalization and budget controls offline."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from anthropic.types import Message

from specx.evalx.llm import AnthropicLLM, BudgetExceededError, FakeLLM


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECX_AGENT_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("SPECX_BUDGET_USD", "60")


def sdk() -> SimpleNamespace:
    message = Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-sonnet-5-5",
        content=[{"type": "text", "text": "Done"}],
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 2},
    )
    return SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=message)))


def test_adapter_uses_sdk_and_handles_optional_null_cache_usage(configured: None) -> None:
    provider = sdk()
    llm = AnthropicLLM(sdk=provider)
    result = llm.create(
        model=llm.model, messages=[], max_tokens=4096, output_config={"effort": "medium"}
    )
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["cache_read_input_tokens"] == 0
    assert llm.spent_usd == pytest.approx(0.00004)
    assert provider.messages.create.call_args.kwargs["output_config"] == {"effort": "medium"}


def test_adapter_refuses_model_changes(configured: None) -> None:
    provider = sdk()
    with pytest.raises(ValueError, match="frozen"):
        AnthropicLLM(sdk=provider).create(model="different")
    provider.messages.create.assert_not_called()
    llm = AnthropicLLM(sdk=provider)
    with pytest.raises(AttributeError):
        llm.model = "different"


def test_budget_blocks_before_request_when_already_exhausted(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECX_BUDGET_USD", "0")
    provider = sdk()
    llm = AnthropicLLM(sdk=provider)
    with pytest.raises(BudgetExceededError, match="SPECX_BUDGET_USD exhausted"):
        llm.create(model=llm.model)
    provider.messages.create.assert_not_called()


def test_budget_aborts_before_executing_tools_when_response_exceeds_limit(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECX_BUDGET_USD", "0.000001")
    llm = AnthropicLLM(sdk=sdk())
    with pytest.raises(BudgetExceededError):
        llm.create(model=llm.model)
    assert llm.spent_usd > llm.limit_usd


def test_spend_prints_every_fifty_episodes(
    configured: None, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = AnthropicLLM(sdk=sdk())
    for _ in range(50):
        llm.episode_finished()
    assert "50 episodes" in capsys.readouterr().err


def test_configuration_is_explicit_and_fake_never_uses_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECX_AGENT_MODEL", raising=False)
    with pytest.raises(ValueError, match="SPECX_AGENT_MODEL"):
        AnthropicLLM(sdk=sdk())
    fake = FakeLLM([{"stop_reason": "end_turn", "content": [], "usage": {}}], model="offline-model")
    assert fake.create(model="offline-model")["stop_reason"] == "end_turn"
    with pytest.raises(RuntimeError, match="exhausted"):
        fake.create(model="offline-model")
