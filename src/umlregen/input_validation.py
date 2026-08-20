"""Input validation (T4.12): every image is opened and checked through
Pillow *before* it reaches the model or gets written anywhere, so a
decompression bomb, a wrong-format file (even one lying about its own
extension), or plain corrupt data is rejected with a clear, typed
message -- not a Pillow traceback or an unbounded-memory hang the first
time a user (or an adversarial input) hits it.
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from umlregen.errors import InvalidImage

# Conservative on purpose: every corpus/holdout image is well under 1
# megapixel, and a real screenshot or documentation figure has no reason
# to approach this. Far below Pillow's own default (89,478,485) so this
# is the limit that actually fires, not a dead configuration.
MAX_IMAGE_PIXELS = 40_000_000  # ~40 megapixels, e.g. 6350x6350

_ALLOWED_FORMATS = {"PNG", "JPEG"}


def validate_image(image_path: str | Path) -> bytes:
    """Reads and validates `image_path`, returning its raw bytes if it
    passes. Raises `InvalidImage` naming the specific problem:

    - Too many pixels (checked via Pillow's own `MAX_IMAGE_PIXELS`
      decompression-bomb detection, with its warning promoted to an
      error so an image between 1x-2x the limit is rejected outright
      rather than merely warned about -- Pillow's own default only
      *raises* past 2x the configured limit).
    - Format outside the allowlist, checked against the image's actual
      decoded format (`Image.format`), not its file extension -- a
      `.txt` renamed to `.png` is caught here, not waved through.
    - Unreadable/corrupt data.
    """
    image_path = Path(image_path)
    image_bytes = image_path.read_bytes()

    original_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    img.verify()  # cheap structural check; invalidates further use of `img`
                with Image.open(io.BytesIO(image_bytes)) as img:
                    fmt = img.format
                    img.load()  # decodes -- the actual point the pixel-count check fires
            except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise InvalidImage(
                    f"{image_path} exceeds the {MAX_IMAGE_PIXELS:,}-pixel limit "
                    f"({exc}) -- looks like a decompression bomb, not a legitimate diagram."
                ) from exc
            except UnidentifiedImageError as exc:
                raise InvalidImage(f"{image_path} is not a readable image: {exc}") from exc
            except InvalidImage:
                raise
            except Exception as exc:  # noqa: BLE001 -- Pillow raises format-specific error types
                raise InvalidImage(f"{image_path} could not be read as an image: {exc}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit

    if fmt not in _ALLOWED_FORMATS:
        raise InvalidImage(
            f"{image_path} has format {fmt!r} (detected from content, not its file "
            f"extension), which is not one of the supported formats {sorted(_ALLOWED_FORMATS)}."
        )

    return image_bytes
