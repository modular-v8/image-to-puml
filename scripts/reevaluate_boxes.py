"""T3.11 retry: re-runs the OpenCV contour fallback with the new
count-aware adaptive threshold (boxes.py, 2026-08-20) against the exact
same corpus + holdout set T3.11 originally evaluated (now 8 holdout
diagrams, not 4, per T3.40's expansion). $0 cost -- purely local, no
model calls. Prints box count vs. expected class count per diagram, and
writes a debug overlay per diagram for visual inspection, the same
methodology T3.11 used originally."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from umlregen.ir.models import Diagram
from umlregen.perception.boxes import extract_boxes_contours
from umlregen.perception.overlay import draw_overlay

overlay_dir = Path("runs/debug/box_overlays_retry")

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


rows = []
for ir_dir, img_dir, set_name in [
    (Path("corpus/ir"), Path("corpus/img"), "corpus"),
    (Path("corpus/holdout/ir"), Path("corpus/holdout/img"), "holdout"),
]:
    for ir_path in sorted(ir_dir.glob("*.json")):
        name = ir_path.stem
        img_path = _find_image(img_dir, name)
        if img_path is None:
            print(f"SKIP {name}: no image found")
            continue
        expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        image_bytes = img_path.read_bytes()
        expected_count = len(expected.classes)

        boxes = extract_boxes_contours(image_bytes, expected_count=expected_count)
        rows.append((set_name, name, expected_count, len(boxes)))

        labelled = {f"box_{i}": b for i, b in enumerate(boxes)}
        draw_overlay(image_bytes, labelled, overlay_dir / f"{set_name}_{name}.png")

print(f"{'set':<8} {'diagram':<32} {'expected':>8} {'found':>6} {'match':>6}")
exact_matches = 0
for set_name, name, expected_count, found_count in rows:
    match = "YES" if expected_count == found_count else "no"
    if expected_count == found_count:
        exact_matches += 1
    print(f"{set_name:<8} {name:<32} {expected_count:>8} {found_count:>6} {match:>6}")

print(f"\nExact count matches: {exact_matches}/{len(rows)}")
print(f"Overlays written to: {overlay_dir}")
