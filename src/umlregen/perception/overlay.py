"""T3.10: a debug overlay drawing detected boxes with labels onto the
source image. Purely a visualization aid for T3.11's quality gate and,
later, `--debug-dir` (T4.2) -- no return value is consumed by the
pipeline itself.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from umlregen.ir.models import BBox

_BOX_COLOR = (220, 30, 30)
_LABEL_BG = (220, 30, 30)
_LABEL_FG = (255, 255, 255)


def draw_overlay(
    image_bytes: bytes, boxes: dict[str, BBox], out_path: Path
) -> Path:
    """Draws each `(label, BBox)` pair as a labelled rectangle onto a copy
    of the source image, and writes it to `out_path`. `boxes` keys are
    whatever label the caller wants shown -- a class id/name for the
    model-grounding path, or a synthetic index like "box_0" for the
    unnamed contour fallback.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)

    for label, box in boxes.items():
        draw.rectangle(
            [box.x, box.y, box.x + box.w, box.y + box.h], outline=_BOX_COLOR, width=2
        )
        text_bbox = draw.textbbox((box.x, box.y), label)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        label_y = box.y - text_h - 4 if box.y - text_h - 4 >= 0 else box.y
        draw.rectangle(
            [box.x, label_y, box.x + text_w + 4, label_y + text_h + 4], fill=_LABEL_BG
        )
        draw.text((box.x + 2, label_y + 2), label, fill=_LABEL_FG)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path
