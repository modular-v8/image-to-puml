"""Offline tests for T3.5: a relationship with empty or boilerplate
evidence triggers the repair-retry, same mechanism as a schema
validation failure. Also T3.41: if the retry *still* has no usable
evidence, the relationship degrades to floor confidence with a warning
instead of the whole diagram being discarded. No network."""

from typing import Any

from umlregen.ir.models import Diagram
from umlregen.perception.client import VisionResponse
from umlregen.perception.extract import extract_relationships


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        self.prompts.append(prompt)
        return self._responses.pop(0)


_STAGE_A = Diagram.model_validate(
    {
        "classes": [
            {"id": "A", "name": "A", "kind": "class", "attributes": [], "methods": []},
            {"id": "B", "name": "B", "kind": "class", "attributes": [], "methods": []},
        ],
        "relationships": [],
    }
)


def _relationships_response(evidence: str | None) -> dict[str, Any]:
    return {
        "relationships": [
            {
                "source": "A",
                "target": "B",
                "kind": "association",
                "evidence": evidence,
            }
        ]
    }


def test_empty_evidence_triggers_repair_retry() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok", parsed_json=_relationships_response(""), model_id="test/model"
            ),
            VisionResponse(
                raw_text="ok",
                parsed_json=_relationships_response("dashed line, hollow triangle at B"),
                model_id="test/model",
            ),
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(client.prompts) == 2
    assert "boilerplate evidence" in client.prompts[1]
    assert len(diagram.relationships) == 1
    assert diagram.relationships[0].evidence == "dashed line, hollow triangle at B"


def test_boilerplate_evidence_triggers_repair_retry() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok", parsed_json=_relationships_response("N/A"), model_id="test/model"
            ),
            VisionResponse(
                raw_text="ok",
                parsed_json=_relationships_response("solid line, no arrowhead"),
                model_id="test/model",
            ),
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(client.prompts) == 2
    assert len(diagram.relationships) == 1


def test_evidence_still_missing_after_retry_degrades_not_discards() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok", parsed_json=_relationships_response(""), model_id="test/model"
            ),
            VisionResponse(
                raw_text="ok", parsed_json=_relationships_response("n/a"), model_id="test/model"
            ),
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(client.prompts) == 2  # still one repair-retry attempt, not zero
    assert len(diagram.relationships) == 1  # kept, not discarded
    assert diagram.relationships[0].confidence == 0.0
    assert diagram.relationships[0].source == "A"
    assert diagram.relationships[0].target == "B"
    assert len(diagram.warnings) == 1
    assert "floor confidence" in diagram.warnings[0]
    assert "'A' -> 'B'" in diagram.warnings[0]


def test_evidence_still_missing_when_first_attempt_was_unparseable() -> None:
    # The bug T3.41 originally shipped with: if attempt 1 isn't valid JSON
    # at all, `validate` is never called for it (complete_with_repair
    # short-circuits before reaching `validate`). A caller that tries to
    # count its own invocations of `validate` to detect "is this the last
    # attempt" undercounts here -- attempt 2 looks like validate's *first*
    # call, not its second, and the degradation path never fires. The
    # fix is `complete_with_repair` passing `is_last_attempt` explicitly.
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="not json at all", parsed_json=None, model_id="test/model"),
            VisionResponse(
                raw_text="ok", parsed_json=_relationships_response(""), model_id="test/model"
            ),
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(client.prompts) == 2
    assert len(diagram.relationships) == 1  # kept, not discarded
    assert diagram.relationships[0].confidence == 0.0
    assert len(diagram.warnings) == 1


def test_multiple_relationships_only_missing_evidence_one_degrades() -> None:
    def _two_relationships_response(second_evidence: str | None) -> dict[str, Any]:
        return {
            "relationships": [
                {"source": "A", "target": "B", "kind": "association", "evidence": "solid line"},
                {
                    "source": "B",
                    "target": "A",
                    "kind": "dependency",
                    "evidence": second_evidence,
                },
            ]
        }

    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok",
                parsed_json=_two_relationships_response(""),
                model_id="test/model",
            ),
            VisionResponse(
                raw_text="ok",
                parsed_json=_two_relationships_response(None),
                model_id="test/model",
            ),
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(diagram.relationships) == 2
    by_kind = {r.kind.value: r for r in diagram.relationships}
    assert by_kind["association"].confidence != 0.0  # had real evidence throughout
    assert by_kind["dependency"].confidence == 0.0  # the one that never got evidence
    assert len(diagram.warnings) == 1


def test_real_evidence_makes_no_retry() -> None:
    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok",
                parsed_json=_relationships_response("solid line, hollow diamond at A"),
                model_id="test/model",
            )
        ]
    )

    diagram, _cost = extract_relationships(client, b"image-bytes", _STAGE_A)

    assert len(client.prompts) == 1
    assert len(diagram.relationships) == 1
