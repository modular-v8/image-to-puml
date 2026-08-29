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


# ---------------------------------------------------------------------------
# T7.2: force_refresh -- the knob `run` now defaults to, so a stale
# response can never again stand in for a fresh command's answer.
# ---------------------------------------------------------------------------


def test_force_refresh_calls_wrapped_client_even_on_an_identical_repeat(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path, force_refresh=True)

    first = cached.complete(b"image-bytes", "prompt text")
    second = cached.complete(b"image-bytes", "prompt text")

    assert wrapped.call_count == 2
    assert first.parsed_json == {"n": 1}
    assert second.parsed_json == {"n": 2}
    assert cached.cache_hits == 0
    assert cached.cache_misses == 2


def test_force_refresh_still_writes_through_for_a_later_reuse_call(tmp_path: Path) -> None:
    """The write half of the incident's fix: a force_refresh=True caller
    still leaves a fresh entry on disk, so a *different*, later
    force_refresh=False client (e.g. `run --reuse-cache`) can read it."""
    wrapped_a = _CountingClient()
    refreshing = CachedVisionClient(
        wrapped_a, model_id="test/model", cache_dir=tmp_path, force_refresh=True
    )
    refreshing.complete(b"image-bytes", "prompt text")

    wrapped_b = _CountingClient()
    reusing = CachedVisionClient(
        wrapped_b, model_id="test/model", cache_dir=tmp_path, force_refresh=False
    )
    reused = reusing.complete(b"image-bytes", "prompt text")

    assert wrapped_b.call_count == 0  # never touched -- served from what refreshing wrote
    assert reused.parsed_json == {"n": 1}


def test_cache_hits_and_misses_are_counted(tmp_path: Path) -> None:
    wrapped = _CountingClient()
    cached = CachedVisionClient(wrapped, model_id="test/model", cache_dir=tmp_path)

    cached.complete(b"image-bytes", "prompt")  # miss
    cached.complete(b"image-bytes", "prompt")  # hit
    cached.complete(b"image-bytes", "prompt v2")  # miss (different prompt)

    assert cached.cache_misses == 2
    assert cached.cache_hits == 1
