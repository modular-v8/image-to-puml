"""Per-class bounding boxes (T3.8/T3.9): the model-grounding path first,
an OpenCV contour fallback second. Boxes gate the per-connector crop pass
(`connectors.py`) -- nothing is built on top of either path until T3.11's
visual quality check passes, per plan.md's Tech Stack table.
"""

from __future__ import annotations

import io
import json
from typing import Any

import cv2
import numpy as np
from PIL import Image

from umlregen.ir.models import BBox, Diagram
from umlregen.perception.client import VisionClient
from umlregen.perception.prompts import load_prompt
from umlregen.perception.repair import complete_with_repair

_BOX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "w": {"type": "integer"},
                    "h": {"type": "integer"},
                },
                "required": ["name", "x", "y", "w", "h"],
            },
        }
    },
    "required": ["boxes"],
}


def _format_class_list(diagram: Diagram) -> str:
    return "\n".join(f"- {cls.name}" for cls in diagram.classes)


def extract_boxes_model(
    client: VisionClient, image: bytes, classes: Diagram
) -> tuple[dict[str, BBox], float]:
    """Asks the vision model directly for each class's bounding box, in
    source-image pixel coordinates. Returns `{Class.id: BBox}` -- classes
    the model didn't return a box for, or returned an invalid one for
    (degenerate, or out of the image bounds), are simply absent from the
    result rather than failing the whole call; a completely empty result
    is what triggers the repair-retry, on the theory that *some* boxes
    almost always exist on a real diagram and an empty response is more
    likely a formatting miss than a genuinely boxless diagram.
    """
    img_w, img_h = Image.open(io.BytesIO(image)).size
    prompt = load_prompt(
        "extract_boxes",
        class_list=_format_class_list(classes),
        width=str(img_w),
        height=str(img_h),
        schema=json.dumps(_BOX_SCHEMA),
    )
    name_to_id = {cls.name: cls.id for cls in classes.classes}

    def validate(data: dict[str, Any], is_last_attempt: bool) -> dict[str, BBox]:
        boxes: dict[str, BBox] = {}
        for entry in data.get("boxes", []):
            class_id = name_to_id.get(entry.get("name"))
            if class_id is None:
                continue  # a box for a class outside the known list; ignore it
            x, y, w, h = entry.get("x"), entry.get("y"), entry.get("w"), entry.get("h")
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, w, h)):
                continue
            if w <= 0 or h <= 0:
                continue  # degenerate
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                continue  # out of the image's own bounds
            boxes[class_id] = BBox(x=x, y=y, w=w, h=h)
        if not boxes:
            raise ValueError("no valid bounding boxes in response")
        return boxes

    return complete_with_repair(client, image, prompt, _BOX_SCHEMA, validate)


# OpenCV contour fallback (T3.9): zero quota cost, no model call. Works on
# clean, high-contrast renders where class boxes are literal rectangles --
# not expected to survive a JPEG-compressed screenshot as well as the
# model-grounding path, which is exactly the comparison T3.11 makes.
# Tuned against the gate diagram (8 classes, 565x640): the naive
# thresholds let through both small glyph/icon contours (visibility
# markers, arrowheads -- ~500px, nowhere near a whole class box) and the
# diagram's own outer frame (~83% of the image), neither of which is a
# class. 1% as a floor and 50% as a ceiling separates real class boxes
# from both without needing per-diagram tuning.
_MIN_BOX_AREA_FRACTION = 0.01
_MAX_BOX_AREA_FRACTION = 0.50
_MIN_ASPECT_RATIO = 0.15
_MAX_ASPECT_RATIO = 8.0
# A box is dropped as a nested duplicate (a compartment divider, or the
# inner edge of a stroked rectangle) when at least this fraction of its
# own area overlaps a larger box that's being kept.
_CONTAINMENT_OVERLAP_FRACTION = 0.85


# T3.11 retry (2026-08-20): the diagnosed 4th root cause -- a single
# fixed `_MIN_BOX_AREA_FRACTION` isn't scale-invariant, so real class
# boxes on a smaller/denser diagram fall below the same floor that
# correctly filters icon noise on a larger one -- is fixed by no longer
# trusting one global constant. By the time boxes would run in the real
# pipeline, stage A has *already* extracted the class list, so the
# expected class *count* is a known quantity, not a guess. Sweeping the
# min-area-fraction threshold and keeping whichever value's resulting box
# count lands closest to that already-known count turns a fixed
# per-corpus constant into a per-image adaptive one -- exactly what
# T3.11's own write-up concluded was needed, not one more fixed-constant
# tuning pass.
_CANDIDATE_MIN_FRACTIONS = (
    0.0005, 0.001, 0.002, 0.003, 0.005, 0.008, 0.01, 0.015, 0.02, 0.03, 0.05, 0.08, 0.12,
)


def _contour_candidates_at_threshold(
    img: np.ndarray, img_area: int, min_fraction: float
) -> list[BBox]:
    """One threshold's worth of the pipeline: both polarities (keeping
    whichever finds more), area/aspect filtering, containment
    suppression. Factored out so `extract_boxes_contours` can call it
    once per candidate `min_fraction` during a count-aware sweep, or
    once at the fixed default when no expected count is known.
    """
    candidates: list[BBox] = []
    for flag in (cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY):
        _, thresh = cv2.threshold(img, 0, 255, flag + cv2.THRESH_OTSU)
        # RETR_EXTERNAL was tried and dropped: relationship lines touch
        # class borders, so thresholded boxes and their connecting lines
        # merge into one connected blob per diagram, and only its
        # (oversized) outer contour survives -- nothing usable. RETR_LIST
        # finds every contour, including each class's own outline and its
        # internal compartment dividers as separate nested contours; the
        # containment filter below discards the dividers, keeping only
        # outermost boxes.
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        polarity_candidates: list[BBox] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w <= 0 or h <= 0:
                continue
            area_fraction = (w * h) / img_area
            if area_fraction < min_fraction or area_fraction > _MAX_BOX_AREA_FRACTION:
                continue
            aspect_ratio = w / h
            if aspect_ratio < _MIN_ASPECT_RATIO or aspect_ratio > _MAX_ASPECT_RATIO:
                continue
            polarity_candidates.append(BBox(x=x, y=y, w=w, h=h))
        if len(polarity_candidates) > len(candidates):
            candidates = polarity_candidates

    # Largest first, so a class's outer box is always considered before
    # its own (smaller) internal compartment dividers.
    candidates.sort(key=lambda b: b.w * b.h, reverse=True)

    boxes: list[BBox] = []
    for box in candidates:
        box_area = box.w * box.h
        if any(_overlap_area(box, kept) / box_area >= _CONTAINMENT_OVERLAP_FRACTION for kept in boxes):
            continue  # mostly contained within an already-kept, larger box
        boxes.append(box)
    return boxes


def extract_boxes_contours(image: bytes, *, expected_count: int | None = None) -> list[BBox]:
    """Finds rectangular class boxes via thresholding and contour
    detection. Returns boxes in no particular order and with no class
    names attached -- unlike the model-grounding path, contours alone
    can't say *which* class a rectangle belongs to; that association is
    left to the caller (e.g. by nearest-match against stage A's class
    count, or simply for the debug overlay in T3.10).

    `expected_count`, when given (stage A's class count is always known
    by the time this would run for real), drives a sweep over candidate
    min-area-fraction thresholds, keeping whichever produces a box count
    closest to it -- see the module comment above `_CANDIDATE_MIN_FRACTIONS`.
    `None` falls back to the original single fixed threshold, unchanged
    from T3.9.
    """
    array = np.frombuffer(image, dtype=np.uint8)
    img = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("could not decode image for contour detection")

    img_h, img_w = img.shape[:2]
    img_area = img_w * img_h

    if expected_count is None:
        return _contour_candidates_at_threshold(img, img_area, _MIN_BOX_AREA_FRACTION)

    best_boxes: list[BBox] = []
    best_diff = None
    for min_fraction in _CANDIDATE_MIN_FRACTIONS:
        boxes = _contour_candidates_at_threshold(img, img_area, min_fraction)
        diff = abs(len(boxes) - expected_count)
        if best_diff is None or diff < best_diff or (diff == best_diff and len(boxes) > len(best_boxes)):
            best_diff = diff
            best_boxes = boxes
        if diff == 0:
            break
    return best_boxes


def _overlap_area(a: BBox, b: BBox) -> int:
    x_overlap = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    y_overlap = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return x_overlap * y_overlap
