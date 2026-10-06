"""ClaudeAgentClient's error mapping and parsing, offline: the SDK's
`query` is replaced, so no CLI subprocess and no account are involved."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from umlregen.errors import DependencyMissing, ProviderRateLimited, UmlRegenError
from umlregen.perception.claude_agent import ClaudeAgentClient


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, messages: list[Any]) -> None:
    class AssistantMessage:
        def __init__(self, content: list[Any]) -> None:
            self.content = content

    class TextBlock:
        def __init__(self, text: str) -> None:
            self.text = text

    class ResultMessage:
        def __init__(self, **fields: Any) -> None:
            self.__dict__.update(
                dict(is_error=False, errors=None, result=None, usage=None, total_cost_usd=None,
                     stop_reason=None, api_error_status=None, subtype="success"),
                **fields,
            )

    async def query(*, prompt: Any, options: Any) -> Any:
        async for _ in prompt:
            pass
        for message in messages:
            item = message(AssistantMessage, TextBlock, ResultMessage)
            if isinstance(item, Exception):
                raise item
            yield item

    class ClaudeSDKError(Exception):
        pass

    class ResultError(ClaudeSDKError):
        def __init__(self, message: str, **fields: Any) -> None:
            super().__init__(message)
            self.__dict__.update(dict(errors=[], result=None, subtype=None, api_error_status=None), **fields)

    module = types.SimpleNamespace(
        AssistantMessage=AssistantMessage,
        ClaudeAgentOptions=lambda **kw: kw,
        CLINotFoundError=type("CLINotFoundError", (ClaudeSDKError,), {}),
        ClaudeSDKError=ClaudeSDKError,
        ResultError=ResultError,
        ResultMessage=ResultMessage,
        TextBlock=TextBlock,
        query=query,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", module)


def test_returns_parsed_json_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_sdk(
        monkeypatch,
        [lambda A, T, R: R(result='```json\n{"a": 1}\n```', total_cost_usd=0.02,
                           usage={"input_tokens": 5, "output_tokens": 7})],
    )

    response = ClaudeAgentClient(model_id="claude-opus-5-5").complete(b"\x89PNG\r\n\x1a\n", "p")

    assert response.parsed_json == {"a": 1}
    assert response.cost_usd == 0.02
    assert (response.prompt_tokens, response.completion_tokens) == (5, 7)
    assert response.model_id == "claude-opus-5-5"


def test_rate_limit_maps_to_provider_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_sdk(monkeypatch, [lambda A, T, R: R(is_error=True, api_error_status=429)])

    with pytest.raises(ProviderRateLimited):
        ClaudeAgentClient(model_id="claude-opus-5-5").complete(b"x", "p")


def test_other_errors_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_sdk(monkeypatch, [lambda A, T, R: R(is_error=True, result="boom")])

    with pytest.raises(UmlRegenError, match="boom"):
        ClaudeAgentClient(model_id="claude-opus-5-5").complete(b"x", "p")


def test_missing_sdk_is_dependency_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    with pytest.raises(DependencyMissing):
        ClaudeAgentClient(model_id="claude-opus-5-5").complete(b"x", "p")


def test_unknown_model_error_result_is_a_clean_message(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "There's an issue with the selected model (claude-opus-5.5)."
    _install_fake_sdk(monkeypatch, [lambda A, T, R: sys.modules["claude_agent_sdk"].ResultError(text, result=text)])

    with pytest.raises(UmlRegenError, match="selected model"):
        ClaudeAgentClient(model_id="claude-opus-5.5").complete(b"x", "p")
