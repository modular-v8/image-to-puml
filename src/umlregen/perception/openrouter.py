"""`VisionClient` implementation against OpenRouter's OpenAI-compatible
chat completions endpoint. The only place OpenRouter-specific request/
response shapes are allowed to exist -- everything above this module talks
to `VisionClient`/`VisionResponse` only.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import httpx

from umlregen.errors import ProviderAuthError, ProviderRateLimited, RepetitionDetected, ResponseTruncated
from umlregen.perception.client import VisionResponse
from umlregen.perception.reliability import detect_repetition

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

# Found 2026-08-18 (T3.37): with no cap, this model occasionally enters a
# degenerate repetition loop (garbage tokens, not real content -- seen
# both as a wall of literal "<pad>" tokens and, worse, as whatever
# produced a 2 million-character response) and generates until it hits
# whatever ceiling the provider enforces (observed once at 65536
# completion tokens) instead of stopping at a normal response. At roughly
# 60 tokens/second that one call alone took on the order of 18 minutes --
# the actual cause of this project's multi-hour eval runs, not base model
# speed: every legitimate response this project has ever recorded is
# under 1000 completion tokens (T2.6: 47-290 typical; the widest seen
# since is 716). Capping bounds the worst case to roughly a minute
# instead of leaving it uncapped, and doubles as an early cutoff for the
# degenerate case specifically, not just a cost control.
_DEFAULT_MAX_COMPLETION_TOKENS = 4096

# T4.17, found via T3.28's ceiling experiment: the cap above bounds worst-
# case damage but was tuned against a more compact model, and a more
# verbose model can hit it while producing entirely legitimate content
# (confirmed live on `library_system`/`visitor_pattern`'s stage-B calls --
# raising the cap to this value made both complete correctly). Used only
# for the single truncation retry below, never as the default, so the
# T3.37 degenerate-loop protection stays in force for every normal call.
_DEFAULT_TRUNCATION_RETRY_MAX_TOKENS = 12000

# T5.3, decided 2026-08-20 against T4.22's evidence: 4/4 repetition events
# on the shipped model cleared on one plain, unmodified re-ask, and a
# separate sweep of 32 real cached responses found zero false positives
# from the detector itself -- so a single retry is cheap and effective
# here. Deliberately small and configurable rather than retry-until-
# success: T3.28 saw persistent repetition on the frontier ceiling model
# that a raised cap did not converge, so an unbounded retry policy would
# be the wrong default for every model this client might point at.
_DEFAULT_REPETITION_RETRY_ATTEMPTS = 1


def _sniff_image_mime(image: bytes) -> str:
    if image[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"


def _best_effort_json(text: str) -> Any:
    """Tries a direct parse, then a parse with markdown code fences
    stripped. This is deliberately shallow -- the real repair-retry (on
    schema validation failure, with the error fed back to the model) lives
    in extract.py, not here. This is just enough to populate
    `parsed_json` for the common case of a model wrapping JSON in a
    ```json fence.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        try:
            return json.loads(stripped.strip())
        except json.JSONDecodeError:
            return None
    return None


class OpenRouterClient:
    """Talks to OpenRouter. `complete()` maps 401 -> ProviderAuthError
    (no retry, key never echoed) and 429 -> ProviderRateLimited (retried
    with exponential backoff first). Transport/timeout errors are retried
    the same way and, if still failing after `_MAX_ATTEMPTS`, propagate as
    the underlying httpx exception rather than a typed one -- there's
    nothing provider-specific to say about a dropped connection.

    Also throttles proactively: before each request, it waits out whatever
    remains of the minimum gap implied by `requests_per_minute`, so a free
    model's 20-requests-per-minute cap is respected by construction rather
    than discovered via 429s. This is deliberate latency, not a bug -- a
    slow, zero-cost run beats a fast one that spends the day retrying.
    """

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str | None = None,
        base_url: str = _API_URL,
        timeout: float = 60.0,
        requests_per_minute: float = 20.0,
        max_completion_tokens: int = _DEFAULT_MAX_COMPLETION_TOKENS,
        truncation_retry_max_tokens: int = _DEFAULT_TRUNCATION_RETRY_MAX_TOKENS,
        repetition_retry_attempts: int = _DEFAULT_REPETITION_RETRY_ATTEMPTS,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ProviderAuthError("OPENROUTER_API_KEY is not set")
        self._model_id = model_id
        self._base_url = base_url
        self._timeout = timeout
        self._min_interval_seconds = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._max_completion_tokens = max_completion_tokens
        self._truncation_retry_max_tokens = truncation_retry_max_tokens
        self._repetition_retry_attempts = repetition_retry_attempts
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self._min_interval_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            remaining = self._min_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        """T5.3: on `RepetitionDetected`, reissues the entire call fresh
        and unmodified -- same prompt, same starting cap, no cache
        involvement -- up to `repetition_retry_attempts` times (default 1)
        before giving up. Evidence for this policy is T4.22: all 4
        repetition events observed on the shipped model cleared on a
        single plain re-ask, with zero false positives across 32 real
        responses swept separately -- a transient decoding fluke on this
        model, not the persistent loop T3.28 saw on the frontier ceiling
        model (where a retry would not be expected to help, hence the
        count staying small and configurable rather than retry-until-
        success). Delegates the actual attempt, including the existing
        truncation-vs-repetition handling below, to `_complete_checked`.
        """
        attempts = self._repetition_retry_attempts + 1
        for attempt in range(attempts):
            try:
                return self._complete_checked(image, prompt, schema)
            except RepetitionDetected:
                if attempt == attempts - 1:
                    raise
        raise AssertionError("unreachable: loop always returns or raises")

    def _complete_checked(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None
    ) -> VisionResponse:
        """T4.17/T4.18: on a response that hit the token cap
        (`finish_reason == "length"`), checks for T3.37/T3.28's repetition
        pathology first -- a looping response is never worth retrying at a
        higher cap, only more expensive -- and otherwise retries exactly
        once with the cap raised. A response still truncated (and still
        not a repetition loop) after that retry raises `ResponseTruncated`
        rather than handing callers a response no downstream parser can
        trust. No code path above this one ever sees a `finish_reason ==
        "length"` response.
        """
        first = self._complete_once(image, prompt, schema, self._max_completion_tokens)
        if first.finish_reason != "length":
            return first

        if detect_repetition(first.raw_text):
            raise RepetitionDetected(
                f"Model {self._model_id!r} entered a degenerate repetition loop "
                "(a short unit repeated many times consecutively) instead of "
                "producing valid content -- see T3.37/T4.18.",
                raw_response=first.raw_text,
            )

        retry = self._complete_once(image, prompt, schema, self._truncation_retry_max_tokens)
        combined = retry.model_copy(
            update={
                "cost_usd": first.cost_usd + retry.cost_usd,
                "prompt_tokens": first.prompt_tokens + retry.prompt_tokens,
                "completion_tokens": first.completion_tokens + retry.completion_tokens,
            }
        )
        if combined.finish_reason != "length":
            return combined

        if detect_repetition(combined.raw_text):
            raise RepetitionDetected(
                f"Model {self._model_id!r} entered a degenerate repetition loop "
                "even at the raised token cap -- see T3.37/T4.18.",
                raw_response=combined.raw_text,
            )

        raise ResponseTruncated(
            f"Model {self._model_id!r} truncated at {self._max_completion_tokens} tokens "
            f"and again at the raised cap of {self._truncation_retry_max_tokens} tokens -- "
            "see T3.28/T4.17.",
            raw_response=combined.raw_text,
            token_cap=self._truncation_retry_max_tokens,
        )

    def _complete_once(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None, max_tokens: int
    ) -> VisionResponse:
        mime = _sniff_image_mime(image)
        b64 = base64.b64encode(image).decode("ascii")

        body: dict[str, Any] = {
            "model": self._model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            "usage": {"include": True},
            "max_tokens": max_tokens,
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "diagram_ir", "schema": schema, "strict": False},
            }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        data = self._post_with_retry(body, headers)

        # OpenRouter can return HTTP 200 with an embedded error object rather
        # than an HTTP error status -- observed with an upstream model timeout
        # (`{"error": {"code": 504, "message": "Upstream idle timeout
        # exceeded"}}`). Surface that clearly instead of a bare KeyError on
        # the missing "choices" key.
        if "choices" not in data and "error" in data:
            error = data["error"]
            raise RuntimeError(
                f"OpenRouter returned an error for model {self._model_id!r} "
                f"despite a 200 status: {error.get('message', error)!r} "
                f"(code {error.get('code', 'unknown')})"
            )

        choice = data["choices"][0]
        message_content = choice["message"]["content"]
        usage = data.get("usage") or {}

        return VisionResponse(
            raw_text=message_content,
            parsed_json=_best_effort_json(message_content),
            model_id=data.get("model", self._model_id),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cost_usd=usage.get("cost", 0.0),
            finish_reason=choice.get("finish_reason"),
        )

    def _post_with_retry(
        self, body: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        for attempt in range(_MAX_ATTEMPTS):
            is_last_attempt = attempt == _MAX_ATTEMPTS - 1

            self._throttle()
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(self._base_url, json=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError):
                if is_last_attempt:
                    raise
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue

            if response.status_code == 401:
                raise ProviderAuthError("OpenRouter rejected the API key (401)")

            if response.status_code == 429:
                if is_last_attempt:
                    # T5.12: plan.md's error table always said this should
                    # suggest --model; a real dogfooding run on the free-tier
                    # interactive default hit exactly this and the message
                    # suggested nothing. Free and paid tiers share the same
                    # base id in this project's naming convention (a bare
                    # ":free" suffix), so the suggestion can be derived
                    # rather than hardcoded.
                    if self._model_id.endswith(":free"):
                        suggestion = (
                            f" The free tier can get congested under load -- try "
                            f"--model {self._model_id.removesuffix(':free')} for the paid "
                            "tier (a fraction of a cent per diagram), or retry shortly."
                        )
                    else:
                        suggestion = " Try a different model with --model, or retry shortly."
                    raise ProviderRateLimited(
                        f"OpenRouter rate-limited model {self._model_id!r} (429) "
                        f"after {_MAX_ATTEMPTS} attempts.{suggestion}"
                    )
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue

            response.raise_for_status()
            return response.json()

        raise AssertionError("unreachable: loop always returns or raises")
