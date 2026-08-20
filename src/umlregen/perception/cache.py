"""Transparent caching wrapper over any `VisionClient`. Exists from the
first day a provider is called, not added later under quota pressure --
it's also what makes evaluation runs reproducible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from umlregen.perception.client import VisionClient, VisionResponse, cache_key


class CachedVisionClient:
    """Wraps any `VisionClient`, caching responses on disk keyed by image
    content, prompt content, model identifier, and generation parameters
    -- one JSON file per key under `cache_dir`. `schema` is folded into the
    params half of the key: two calls with the same image and prompt text
    but a different requested schema are a genuinely different request,
    not a cache hit.

    A cache hit never touches the wrapped client -- no network call, no
    quota spent, and (for `OpenRouterClient` specifically) no throttle
    delay either, since the wrapped client's `complete()` is simply never
    invoked.
    """

    def __init__(
        self,
        wrapped: VisionClient,
        *,
        model_id: str,
        cache_dir: Path,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._model_id = model_id
        self._cache_dir = Path(cache_dir)
        self._extra_params = params or {}

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        key_params = {**self._extra_params, "schema": schema}
        key = cache_key(image, prompt, self._model_id, key_params)
        cache_path = self._cache_dir / f"{key}.json"

        if cache_path.is_file():
            return VisionResponse.model_validate_json(cache_path.read_text(encoding="utf-8"))

        response = self._wrapped.complete(image, prompt, schema)

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return response
