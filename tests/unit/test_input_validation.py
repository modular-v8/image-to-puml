"""T4.12/T4.15: offline tests for input validation. No network."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from umlregen.errors import InvalidImage
from umlregen.input_validation import MAX_IMAGE_PIXELS, validate_image


def test_valid_png_passes_and_returns_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "diagram.png"
    Image.new("RGB", (20, 20), color="white").save(path, format="PNG")

    result = validate_image(path)

    assert result == path.read_bytes()


def test_valid_jpeg_passes(tmp_path: Path) -> None:
    path = tmp_path / "diagram.jpg"
    Image.new("RGB", (20, 20), color="white").save(path, format="JPEG")

    validate_image(path)  # does not raise


def test_txt_renamed_to_png_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.png"
    path.write_text("this is plain text, not an image", encoding="utf-8")

    with pytest.raises(InvalidImage):
        validate_image(path)


def test_bmp_content_rejected_despite_png_extension(tmp_path: Path) -> None:
    # A real, valid image -- just not in the allowlist -- proves the
    # format check reads decoded content, not the file's own extension.
    path = tmp_path / "diagram.png"
    Image.new("RGB", (20, 20), color="white").save(path, format="BMP")

    with pytest.raises(InvalidImage, match="format"):
        validate_image(path)


def test_truncated_file_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.png"
    Image.new("RGB", (20, 20), color="white").save(real, format="PNG")
    truncated = tmp_path / "truncated.png"
    truncated.write_bytes(real.read_bytes()[:20])  # header only, no image data

    with pytest.raises(InvalidImage):
        validate_image(truncated)


def test_decompression_bomb_is_rejected(tmp_path: Path) -> None:
    # Comfortably over MAX_IMAGE_PIXELS (a solid color PNG compresses
    # fast regardless of pixel count, so this stays quick).
    side = int((MAX_IMAGE_PIXELS * 1.5) ** 0.5)
    path = tmp_path / "bomb.png"
    Image.new("L", (side, side), color=0).save(path, format="PNG")

    with pytest.raises(InvalidImage, match="pixel limit"):
        validate_image(path)


def test_max_image_pixels_is_restored_after_validation(tmp_path: Path) -> None:
    # validate_image() temporarily overrides PIL's global
    # Image.MAX_IMAGE_PIXELS -- confirms it puts the global back rather
    # than leaking a changed value into anything else that imports PIL.
    original = Image.MAX_IMAGE_PIXELS
    path = tmp_path / "diagram.png"
    Image.new("RGB", (20, 20), color="white").save(path, format="PNG")

    validate_image(path)

    assert Image.MAX_IMAGE_PIXELS == original


def test_at_limit_image_passes_just_over_limit_rejected(tmp_path: Path) -> None:
    # Boundary check: comfortably under the limit passes, comfortably
    # over is rejected -- not asserting the exact pixel-count boundary
    # itself, since Pillow's own bomb check applies its multiplier logic
    # (warning vs. error) rather than a hard single-pixel cutoff.
    under_side = int((MAX_IMAGE_PIXELS * 0.5) ** 0.5)
    under_path = tmp_path / "under.png"
    Image.new("L", (under_side, under_side), color=0).save(under_path, format="PNG")
    validate_image(under_path)  # does not raise

    over_side = int((MAX_IMAGE_PIXELS * 2.5) ** 0.5)
    over_path = tmp_path / "over.png"
    Image.new("L", (over_side, over_side), color=0).save(over_path, format="PNG")
    with pytest.raises(InvalidImage):
        validate_image(over_path)
