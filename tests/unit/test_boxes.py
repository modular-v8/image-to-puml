"""T3.12: offline tests for box geometry -- in-bounds validation and
degenerate-box rejection (model-grounding path), and contour filtering
against synthetic fixture images (OpenCV fallback, including T3.11's
2026-08-20 retry: the count-aware adaptive threshold). No network, no
model call for the contour tests; a scripted VisionClient for the
model-grounding tests.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageDraw

from umlregen.ir.models import Diagram
from umlregen.perception.boxes import extract_boxes_contours, extract_boxes_model
from umlregen.perception.client import VisionResponse

# ---------------------------------------------------------------------------
# extract_boxes_model: in-bounds validation, degenerate-box rejection
# ---------------------------------------------------------------------------

_IMG_W, _IMG_H = 500, 400
_DIAGRAM = Diagram(
    classes=[
        {"id": "Foo", "name": "Foo", "kind": "class", "attributes": [], "methods": []},
        {"id": "Bar", "name": "Bar", "kind": "class", "attributes": [], "methods": []},
    ],
    relationships=[],
)


def _tiny_png_bytes(w: int = _IMG_W, h: int = _IMG_H) -> bytes:
    import io

    image = Image.new("RGB", (w, h), color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        return self._responses.pop(0)


def test_valid_boxes_pass_and_out_of_bounds_ones_are_dropped() -> None:
    response = {
        "boxes": [
            {"name": "Foo", "x": 10, "y": 10, "w": 100, "h": 50},  # valid
            {"name": "Bar", "x": 450, "y": 10, "w": 100, "h": 50},  # x + w > img_w
        ]
    }
    client = _ScriptedClient([VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model")])

    boxes, _ = extract_boxes_model(client, _tiny_png_bytes(), _DIAGRAM)

    assert "Foo" in boxes
    assert "Bar" not in boxes
    assert boxes["Foo"].x == 10 and boxes["Foo"].w == 100


def test_negative_coordinates_are_dropped() -> None:
    response = {"boxes": [{"name": "Foo", "x": -5, "y": 10, "w": 100, "h": 50}]}
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
        ]
    )
    # Every box invalid -> triggers the repair-retry, then raises since the
    # retry is scripted identically here.
    from umlregen.errors import ExtractionInvalid

    with pytest.raises(ExtractionInvalid):
        extract_boxes_model(client, _tiny_png_bytes(), _DIAGRAM)


def test_degenerate_boxes_are_dropped() -> None:
    response = {
        "boxes": [
            {"name": "Foo", "x": 10, "y": 10, "w": 0, "h": 50},  # zero width
            {"name": "Bar", "x": 10, "y": 10, "w": 50, "h": -1},  # negative height
        ]
    }
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
        ]
    )
    from umlregen.errors import ExtractionInvalid

    with pytest.raises(ExtractionInvalid):
        extract_boxes_model(client, _tiny_png_bytes(), _DIAGRAM)


def test_box_for_unknown_class_name_is_ignored() -> None:
    response = {
        "boxes": [
            {"name": "Foo", "x": 10, "y": 10, "w": 100, "h": 50},
            {"name": "NotInDiagram", "x": 200, "y": 10, "w": 100, "h": 50},
        ]
    }
    client = _ScriptedClient([VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model")])

    boxes, _ = extract_boxes_model(client, _tiny_png_bytes(), _DIAGRAM)

    assert set(boxes) == {"Foo"}


def test_non_integer_values_are_dropped() -> None:
    response = {"boxes": [{"name": "Foo", "x": 10.5, "y": 10, "w": 100, "h": 50}]}
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=response, model_id="test/model"),
        ]
    )
    from umlregen.errors import ExtractionInvalid

    with pytest.raises(ExtractionInvalid):
        extract_boxes_model(client, _tiny_png_bytes(), _DIAGRAM)


# ---------------------------------------------------------------------------
# extract_boxes_contours: synthetic fixture images, no model, no network
# ---------------------------------------------------------------------------


def _synthetic_diagram_image(rects: list[tuple[int, int, int, int]], size: tuple[int, int] = (600, 400)) -> bytes:
    """Draws `rects` (x, y, w, h) as black-outlined white boxes on a white
    background -- a clean, synthetic stand-in for a class-box layout,
    with ground truth known exactly (unlike a real rendered diagram)."""
    import io

    image = Image.new("L", size, color=255)
    draw = ImageDraw.Draw(image)
    for x, y, w, h in rects:
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=0, width=3)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_contour_detection_finds_well_separated_boxes() -> None:
    rects = [(20, 20, 150, 100), (250, 20, 150, 100), (20, 200, 150, 100)]
    image_bytes = _synthetic_diagram_image(rects)

    boxes = extract_boxes_contours(image_bytes)

    assert len(boxes) == len(rects)
    found_areas = sorted(b.w * b.h for b in boxes)
    expected_areas = sorted(w * h for _, _, w, h in rects)
    # Bounding rect of a drawn outline is close to, not pixel-identical to,
    # the requested rect (stroke width) -- compare with tolerance.
    for found, expected in zip(found_areas, expected_areas):
        assert abs(found - expected) / expected < 0.1


def test_tiny_noise_below_area_floor_is_excluded() -> None:
    rects = [(20, 20, 150, 100)]
    noise = [(400, 20, 5, 5)]  # far below the 1% area floor on a 600x400 image
    image_bytes = _synthetic_diagram_image(rects + noise)

    boxes = extract_boxes_contours(image_bytes)

    assert len(boxes) == 1  # the noise contour never survives filtering


def test_nested_divider_is_suppressed_by_containment() -> None:
    # An outer class box with an inner "compartment divider" rectangle --
    # the inner one should be dropped as contained within the outer.
    outer = (20, 20, 200, 150)
    inner = (30, 90, 180, 10)
    image_bytes = _synthetic_diagram_image([outer, inner])

    boxes = extract_boxes_contours(image_bytes)

    assert len(boxes) == 1
    assert boxes[0].w * boxes[0].h > 150 * 10 * 5  # the outer box survived, not the sliver


def test_count_aware_threshold_recovers_boxes_a_fixed_threshold_would_miss() -> None:
    # Small boxes on a large canvas -- ~0.2% of the image each, comfortably
    # under the fixed 1% floor but within the adaptive sweep's range --
    # reproducing T3.11's diagnosed "not scale-invariant" failure directly.
    small_rects = [(20, 20, 100, 60), (400, 20, 100, 60), (800, 20, 100, 60)]
    image_bytes = _synthetic_diagram_image(small_rects, size=(2000, 1500))

    without_hint = extract_boxes_contours(image_bytes)
    assert len(without_hint) == 0  # the exact failure mode T3.11 diagnosed

    with_hint = extract_boxes_contours(image_bytes, expected_count=3)
    assert len(with_hint) == 3


def test_undecodable_image_raises() -> None:
    with pytest.raises(ValueError):
        extract_boxes_contours(b"not an image at all")
