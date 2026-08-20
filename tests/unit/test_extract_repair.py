"""Offline tests for the repair-retry (T2.12): a malformed response
triggers exactly one retry with the validation error appended to the
prompt; a response that's still invalid after the retry raises
ExtractionInvalid with the raw text retrievable. No network."""

from typing import Any

import pytest

from umlregen.errors import ExtractionInvalid
from umlregen.perception.client import VisionResponse
from umlregen.perception.extract import extract_classes


class _ScriptedClient:
    """Returns a pre-scripted sequence of responses, one per call, and
    records the prompts it was called with."""

    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        self.prompts.append(prompt)
        return self._responses.pop(0)


_VALID_CLASSES_JSON = {
    "classes": [{"name": "Foo", "kind": "class", "attributes": [], "methods": []}],
    "relationships": [],
}


def test_malformed_response_triggers_exactly_one_retry_then_succeeds() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="not json at all", parsed_json=None, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_VALID_CLASSES_JSON, model_id="test/model"),
        ]
    )

    diagram, _cost = extract_classes(client, b"image-bytes")

    assert len(client.prompts) == 2
    assert len(diagram.classes) == 1
    assert diagram.classes[0].name == "Foo"
    assert "failed validation" in client.prompts[1]


def test_still_invalid_after_retry_raises_extraction_invalid_with_raw_text() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="garbage 1", parsed_json=None, model_id="test/model"),
            VisionResponse(raw_text="garbage 2", parsed_json=None, model_id="test/model"),
        ]
    )

    with pytest.raises(ExtractionInvalid) as exc_info:
        extract_classes(client, b"image-bytes")

    assert len(client.prompts) == 2
    assert exc_info.value.raw_response == "garbage 2"


def test_valid_first_response_makes_no_retry() -> None:
    client = _ScriptedClient(
        [VisionResponse(raw_text="ok", parsed_json=_VALID_CLASSES_JSON, model_id="test/model")]
    )

    diagram, _cost = extract_classes(client, b"image-bytes")

    assert len(client.prompts) == 1
    assert len(diagram.classes) == 1


def test_pydantic_validation_failure_also_triggers_retry() -> None:
    # Missing the required "kind" field -- a Pydantic ValidationError,
    # not just a JSON-parse failure, and the retry must catch this too.
    invalid_json = {
        "classes": [{"name": "Foo", "attributes": [], "methods": []}],
        "relationships": [],
    }
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=invalid_json, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_VALID_CLASSES_JSON, model_id="test/model"),
        ]
    )

    diagram, _cost = extract_classes(client, b"image-bytes")

    assert len(client.prompts) == 2
    assert len(diagram.classes) == 1
