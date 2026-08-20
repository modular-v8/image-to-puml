"""Offline tests for CachedVisionClient (T2.5): a repeated call is a cache
hit that skips the wrapped client entirely, any change to image, prompt,
schema, or model id is a cache miss, and a missing/deleted cache directory
is harmless."""

import shutil
from pathlib import Path
from typing import Any

from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.client import VisionResponse


class _CountingClient:
    """A minimal VisionClient that counts calls and returns a response
    tagged with the call count, so a cache hit vs. miss is observable
    without a real provider."""

    def __init__(self) -> None:
        self.call_count = 0

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        self.call_count += 1
        return VisionResponse(
            raw_text="ok", parsed_json={"n": self.call_count}, model_id="test/model"
        )


def test_second_identical_call_is_a_cache_hit(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path)

    first = cached.complete(b"image-bytes", "prompt text")
    second = cached.complete(b"image-bytes", "prompt text")

    assert wrapped.call_count == 1
    assert second.parsed_json == first.parsed_json


def test_different_prompt_is_a_cache_miss(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path)

    cached.complete(b"image-bytes", "prompt v1")
    cached.complete(b"image-bytes", "prompt v2")

    assert wrapped.call_count == 2


def test_different_image_is_a_cache_miss(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path)

    cached.complete(b"image-bytes-a", "prompt")
    cached.complete(b"image-bytes-b", "prompt")

    assert wrapped.call_count == 2


def test_different_schema_is_a_cache_miss(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path)

    cached.complete(b"image-bytes", "prompt", schema={"a": 1})
    cached.complete(b"image-bytes", "prompt", schema={"b": 2})

    assert wrapped.call_count == 2


def test_different_model_id_is_a_cache_miss(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached_a = CachedVisionClient(wrapped, model_id="model/a", cache_dir=tmp_path)
    cached_b = CachedVisionClient(wrapped, model_id="model/b", cache_dir=tmp_path)

    cached_a.complete(b"image-bytes", "prompt")
    cached_b.complete(b"image-bytes", "prompt")

    assert wrapped.call_count == 2


def test_missing_cache_directory_is_created_and_harmless(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cache_dir = tmp_path / "does" / "not" / "exist" / "yet"
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=cache_dir)

    response = cached.complete(b"image-bytes", "prompt")

    assert wrapped.call_count == 1
    assert cache_dir.is_dir()
    assert response.parsed_json == {"n": 1}


def test_deleting_cache_directory_is_harmless(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=cache_dir)

    cached.complete(b"image-bytes", "prompt")
    shutil.rmtree(cache_dir)

    response = cached.complete(b"image-bytes", "prompt")

    assert wrapped.call_count == 2
    assert response.parsed_json == {"n": 2}
