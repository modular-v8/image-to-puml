"""The `VisionClient` interface: every provider-specific type stays behind
it. Nothing in `extract.py`, `boxes.py`, or `connectors.py` may import from
`openrouter.py` directly -- they only ever see a `VisionClient` and a
`VisionResponse`, so a local or direct-to-provider backend remains a
drop-in addition later without touching a single call site.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel


def cache_key(image: bytes, prompt: str, model_id: str, params: dict[str, Any]) -> str:
    """The one place the cache/fixture key scheme is defined -- shared by
    `CachedVisionClient` and `FakeVisionClient` so a fixture recorded for
    one is guaranteed addressable by the other, never two independent
    implementations that could quietly drift apart.
    """
    image_hash = hashlib.sha256(image).hexdigest()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    params_repr = json.dumps(params, sort_keys=True, default=str)
    combined = f"{image_hash}:{prompt_hash}:{model_id}:{params_repr}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


class VisionResponse(BaseModel):
    """A provider response, normalized to a model-agnostic shape -- what
    every `VisionClient` implementation returns, regardless of which
    provider or model actually produced it."""

    raw_text: str
    parsed_json: Any = None
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    finish_reason: str | None = None


class VisionClient(Protocol):
    """Structural interface for anything that can answer a vision prompt.

    `schema`, when given, is a JSON Schema the caller would like the
    response constrained to -- an implementation may honour it via
    provider-native structured output, ignore it and rely on the caller's
    own repair-retry, or something in between. Callers must not assume
    either behavior.
    """

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse: ...


class FakeVisionClient:
    """Replays recorded responses from `fixtures_dir`, keyed exactly like
    `CachedVisionClient` (same `cache_key`) -- so it sits at the same seam
    as the real client, and everything above it is under test with no
    network access and no API key. A first-class implementation, not a
    test-only shim.

    A missing fixture is a hard error naming the key, not a silently
    invented response: a made-up response would hide exactly the gap it
    should surface -- this exact request was never recorded against the
    real provider.
    """

    def __init__(
        self,
        *,
        model_id: str,
        fixtures_dir: Path,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._model_id = model_id
        self._fixtures_dir = Path(fixtures_dir)
        self._extra_params = params or {}

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        key_params = {**self._extra_params, "schema": schema}
        key = cache_key(image, prompt, self._model_id, key_params)
        fixture_path = self._fixtures_dir / f"{key}.json"

        if not fixture_path.is_file():
            raise FileNotFoundError(
                f"No recorded fixture for this request (key {key}.json) under "
                f"{self._fixtures_dir}. Record one by running against the real "
                "provider once and committing the response."
            )

        return VisionResponse.model_validate_json(fixture_path.read_text(encoding="utf-8"))
