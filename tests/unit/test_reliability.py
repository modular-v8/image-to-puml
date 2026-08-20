"""T4.21: offline tests for the three failure-mode handlers T3.28
diagnosed -- truncation (T4.17), degenerate repetition (T4.18), and
outright decline (T4.19). No network, no API key: `OpenRouterClient`'s
own HTTP call is monkeypatched at `_post_with_retry`, and decline is
tested directly against `extract_classes` with a scripted `VisionClient`.
"""

from __future__ import annotations

from typing import Any

import pytest

from umlregen.errors import ExtractionDeclined, RepetitionDetected, ResponseTruncated
from umlregen.perception.client import VisionResponse
from umlregen.perception.extract import extract_classes
from umlregen.perception.openrouter import OpenRouterClient
from umlregen.perception.reliability import detect_repetition

# ---------------------------------------------------------------------------
# T4.18: the pure repetition detector, in isolation
# ---------------------------------------------------------------------------


def test_repetition_detector_flags_a_degenerate_loop() -> None:
    looping = "Wait_I_will_do_that_" * 50  # T3.28's observer_pattern failure, shape-for-shape
    assert detect_repetition(looping) is True


def test_repetition_detector_does_not_flag_several_members_typed_str() -> None:
    # The exact false-positive T4.18's acceptance calls out: a legitimate
    # response listing several members that happen to share a type.
    legit = "".join(
        f'{{"name": "{name}", "type": "str"}}, ' for name in ["id", "name", "email", "phone", "address", "notes"]
    )
    assert detect_repetition(legit) is False


def test_repetition_detector_ignores_short_text() -> None:
    assert detect_repetition("short, ordinary response") is False


# ---------------------------------------------------------------------------
# T4.17/T4.18: OpenRouterClient's truncation + repetition orchestration
# ---------------------------------------------------------------------------


def _api_response(*, content: str, finish_reason: str, completion_tokens: int = 100) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 50, "completion_tokens": completion_tokens, "cost": 0.001},
        "model": "test/model",
    }


class _ScriptedPostClient(OpenRouterClient):
    """An `OpenRouterClient` whose `_post_with_retry` is scripted rather
    than hitting the network, so `complete()`'s real orchestration logic
    (truncation retry, repetition short-circuit, cost combination) runs
    exactly as it would in production against canned API bodies.
    """

    def __init__(self, responses: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(model_id="test/model", api_key="test-key", **kwargs)
        self._scripted_responses = list(responses)
        self.call_count = 0

    def _post_with_retry(self, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        self.call_count += 1
        return self._scripted_responses.pop(0)


def test_truncate_then_succeed_returns_the_retry_with_combined_cost() -> None:
    client = _ScriptedPostClient(
        [
            _api_response(content='{"classes": [', finish_reason="length", completion_tokens=4096),
            _api_response(
                content='{"classes": [{"name": "Foo"}]}', finish_reason="stop", completion_tokens=200
            ),
        ]
    )

    result = client.complete(b"image", "prompt", schema={"type": "object"})

    assert result.finish_reason == "stop"
    assert result.raw_text == '{"classes": [{"name": "Foo"}]}'
    assert result.cost_usd == pytest.approx(0.002)
    assert result.completion_tokens == 4296
    assert client.call_count == 2


def test_truncate_twice_raises_response_truncated() -> None:
    client = _ScriptedPostClient(
        [
            _api_response(content='{"classes": [{"name": "A"', finish_reason="length"),
            _api_response(content='{"classes": [{"name": "A", "attributes": [', finish_reason="length"),
        ]
    )

    with pytest.raises(ResponseTruncated) as excinfo:
        client.complete(b"image", "prompt", schema={"type": "object"})

    assert excinfo.value.token_cap == client._truncation_retry_max_tokens
    assert client.call_count == 2


def test_repetition_in_first_attempt_aborts_without_a_retry_call() -> None:
    looping = "Wait_I_will_do_that_" * 60
    client = _ScriptedPostClient([_api_response(content=looping, finish_reason="length")])

    with pytest.raises(RepetitionDetected):
        client.complete(b"image", "prompt", schema={"type": "object"})

    # The whole point of checking repetition before retrying: never spend
    # a second call on a loop that raising the cap won't fix.
    assert client.call_count == 1


def test_repetition_in_retry_attempt_still_raises_repetition_not_truncated() -> None:
    looping = "Wait_I_will_do_that_" * 60
    client = _ScriptedPostClient(
        [
            _api_response(content='{"classes": [{"name": "A"', finish_reason="length"),
            _api_response(content=looping, finish_reason="length"),
        ]
    )

    with pytest.raises(RepetitionDetected):
        client.complete(b"image", "prompt", schema={"type": "object"})

    assert client.call_count == 2


def test_normal_response_is_returned_unchanged() -> None:
    client = _ScriptedPostClient(
        [_api_response(content='{"classes": []}', finish_reason="stop", completion_tokens=50)]
    )

    result = client.complete(b"image", "prompt", schema={"type": "object"})

    assert result.finish_reason == "stop"
    assert result.completion_tokens == 50
    assert client.call_count == 1


# ---------------------------------------------------------------------------
# T4.19: outright decline, tested against extract_classes directly
# ---------------------------------------------------------------------------

_STAGE_A_EMPTY = {"classes": [], "relationships": [], "warnings": ["no classes visible"]}
_STAGE_A_ONE_CLASS = {
    "classes": [{"name": "Recovered", "kind": "class", "attributes": [], "methods": []}],
    "relationships": [],
}


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        self.call_count += 1
        return self._responses.pop(0)


def test_decline_then_succeed_on_reframe() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_EMPTY, model_id="test/model", cost_usd=0.001),
            VisionResponse(
                raw_text="ok", parsed_json=_STAGE_A_ONE_CLASS, model_id="test/model", cost_usd=0.001
            ),
        ]
    )

    diagram, cost = extract_classes(client, b"image")

    assert [c.name for c in diagram.classes] == ["Recovered"]
    assert cost == pytest.approx(0.002)
    assert client.call_count == 2  # exactly one reframed retry, not more


def test_decline_twice_raises_extraction_declined() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
            VisionResponse(raw_text="still nothing", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
        ]
    )

    with pytest.raises(ExtractionDeclined) as excinfo:
        extract_classes(client, b"image")

    assert excinfo.value.raw_response == "still nothing"
    assert client.call_count == 2
