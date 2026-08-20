"""Offline tests for api.py's regenerate() (T2.13): NoClassesFound when
stage A finds nothing, and that a successful run produces a Result whose
.puml actually renders. No network -- uses a scripted VisionClient."""

from pathlib import Path
from typing import Any

import pytest

from umlregen.api import MAX_SUPPORTED_CLASSES, MAX_SUPPORTED_RELATIONSHIPS, regenerate
from umlregen.config import Config
from umlregen.errors import NoClassesFound
from umlregen.perception.client import VisionResponse
from umlregen.render.plantuml import render

from _toolchain import requires_render_toolchain as requires_java

_STAGE_A_EMPTY = {"classes": [], "relationships": []}

_STAGE_A_TWO_CLASSES = {
    "classes": [
        {"name": "Foo", "kind": "class", "attributes": [], "methods": []},
        {"name": "Bar", "kind": "class", "attributes": [], "methods": []},
    ],
    "relationships": [],
}

_STAGE_B_ONE_RELATIONSHIP = {
    "relationships": [
        {
            "source": "Foo",
            "target": "Bar",
            "kind": "association",
            "evidence": "solid line",
        }
    ]
}


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        return self._responses.pop(0)


def test_no_classes_found_when_stage_a_returns_nothing() -> None:
    # T4.19: an empty stage A now triggers exactly one reframed retry
    # inside extract_classes before regenerate() ever sees the result --
    # two empty responses required (original attempt, reframe), not one.
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
            VisionResponse(raw_text="still nothing", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
        ]
    )

    with pytest.raises(NoClassesFound):
        regenerate(b"image-bytes", Config(), client=client)


@requires_java
def test_successful_run_produces_a_result_whose_puml_renders(tmp_path: Path) -> None:
    client = _ScriptedClient(
        [
            VisionResponse(
                raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"
            ),
            VisionResponse(
                raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"
            ),
        ]
    )

    result = regenerate(b"image-bytes", Config(), client=client)

    assert len(result.diagram.classes) == 2
    assert len(result.diagram.relationships) == 1
    assert result.model_id == Config().model_id
    assert result.latency_seconds >= 0

    render(result.puml, "svg", tmp_path / "out.svg")
    assert (tmp_path / "out.svg").is_file()


def test_classes_with_no_relationships_emit_and_warn() -> None:
    # T4.13: this must NOT raise -- classes-but-no-relationships is a
    # degrade-and-warn case, not a failure.
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json={"relationships": []}, model_id="test/model"),
        ]
    )

    result = regenerate(b"image-bytes", Config(), client=client)

    assert len(result.diagram.classes) == 2
    assert len(result.diagram.relationships) == 0
    assert any("no relationships" in w.lower() for w in result.warnings)


def _class(name: str) -> dict:
    return {"name": name, "kind": "class", "attributes": [], "methods": []}


def _relationship(source: str, target: str) -> dict:
    return {"source": source, "target": target, "kind": "association", "evidence": "solid line"}


def test_oversized_diagram_proceeds_best_effort_with_a_bounds_warning() -> None:
    # One more than each bound -- proves the check is a genuine boundary,
    # not just "very large."
    n_classes = MAX_SUPPORTED_CLASSES + 1
    class_names = [f"C{i}" for i in range(n_classes)]
    stage_a = {"classes": [_class(name) for name in class_names], "relationships": []}

    n_relationships = MAX_SUPPORTED_RELATIONSHIPS + 1
    stage_b = {
        "relationships": [
            _relationship(class_names[i % n_classes], class_names[(i + 1) % n_classes])
            for i in range(n_relationships)
        ]
    }

    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=stage_a, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=stage_b, model_id="test/model"),
        ]
    )

    result = regenerate(b"image-bytes", Config(), client=client)

    assert len(result.diagram.classes) == n_classes
    assert len(result.diagram.relationships) == n_relationships
    assert any("exceeding the supported bounds" in w for w in result.warnings)


def test_diagram_at_exactly_the_bounds_does_not_warn() -> None:
    class_names = [f"C{i}" for i in range(MAX_SUPPORTED_CLASSES)]
    stage_a = {"classes": [_class(name) for name in class_names], "relationships": []}
    stage_b = {
        "relationships": [
            _relationship(class_names[i % MAX_SUPPORTED_CLASSES], class_names[(i + 1) % MAX_SUPPORTED_CLASSES])
            for i in range(MAX_SUPPORTED_RELATIONSHIPS)
        ]
    }

    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=stage_a, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=stage_b, model_id="test/model"),
        ]
    )

    result = regenerate(b"image-bytes", Config(), client=client)

    assert not any("exceeding the supported bounds" in w for w in result.warnings)
