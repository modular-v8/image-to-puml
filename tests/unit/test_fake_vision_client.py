"""Offline tests for FakeVisionClient (T2.7): replays fixtures keyed
exactly like CachedVisionClient, so a response recorded through one is
directly addressable through the other. No network, no API key."""

from pathlib import Path

import pytest

from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.client import FakeVisionClient, VisionResponse, cache_key


def _write_fixture(
    fixtures_dir: Path, image: bytes, prompt: str, model_id: str, response: VisionResponse
) -> None:
    key = cache_key(image, prompt, model_id, {"schema": None})
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / f"{key}.json").write_text(response.model_dump_json(indent=2), encoding="utf-8")


def test_replays_a_recorded_fixture(tmp_path: Path) -> None:
    recorded = VisionResponse(raw_text="ok", parsed_json={"n": 1}, model_id="test/model")
    _write_fixture(tmp_path, b"image-bytes", "prompt", "test/model", recorded)

    client = FakeVisionClient(model_id="test/model", fixtures_dir=tmp_path)
    response = client.complete(b"image-bytes", "prompt")

    assert response.parsed_json == {"n": 1}


def test_missing_fixture_raises_clear_error_not_a_silent_stub(tmp_path: Path) -> None:
    client = FakeVisionClient(model_id="test/model", fixtures_dir=tmp_path)

    with pytest.raises(FileNotFoundError, match="No recorded fixture"):
        client.complete(b"unrecorded-image", "unrecorded prompt")


def test_shares_the_cache_s_exact_key_scheme(tmp_path: Path) -> None:
    # A fixture recorded via CachedVisionClient's on-disk format must be
    # directly readable by FakeVisionClient at the identical key. This is
    # the actual point of sharing `cache_key` from client.py rather than
    # each having its own copy that could quietly drift apart.
    class _StubClient:
        def complete(self, image: bytes, prompt: str, schema=None) -> VisionResponse:
            return VisionResponse(
                raw_text="ok", parsed_json={"from": "real_provider"}, model_id="test/model"
            )

    cached = CachedVisionClient(_StubClient(), model_id="test/model", cache_dir=tmp_path)
    cached.complete(b"image-bytes", "prompt")  # writes one cache file

    fake = FakeVisionClient(model_id="test/model", fixtures_dir=tmp_path)
    response = fake.complete(b"image-bytes", "prompt")

    assert response.parsed_json == {"from": "real_provider"}


def test_schema_is_part_of_the_fixture_key(tmp_path: Path) -> None:
    recorded = VisionResponse(raw_text="ok", parsed_json={"with_schema": True}, model_id="test/model")
    key = cache_key(b"image-bytes", "prompt", "test/model", {"schema": {"a": 1}})
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{key}.json").write_text(recorded.model_dump_json(), encoding="utf-8")

    client = FakeVisionClient(model_id="test/model", fixtures_dir=tmp_path)

    with pytest.raises(FileNotFoundError):
        client.complete(b"image-bytes", "prompt", schema=None)  # no fixture at this key

    response = client.complete(b"image-bytes", "prompt", schema={"a": 1})
    assert response.parsed_json == {"with_schema": True}
