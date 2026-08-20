"""The repair-retry, shared across every perception stage that asks a
model for structured JSON: stage A/B classification (extract.py), the
per-class bounding-box pass (boxes.py), and the per-connector pass
(connectors.py). One implementation, so the retry-once-then-raise
behavior can't drift between call sites.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import ValidationError as PydanticValidationError

from umlregen.errors import ExtractionInvalid
from umlregen.perception.client import VisionClient

T = TypeVar("T")


def complete_with_repair(
    client: VisionClient,
    image: bytes,
    prompt: str,
    schema: dict[str, Any],
    validate: Callable[[dict[str, Any], bool], T],
) -> tuple[T, float]:
    """Calls `client.complete()` and applies `validate` to the parsed JSON.
    On failure (not a JSON object, or `validate` raises), re-issues the
    request once with the error appended to the prompt. Raises
    `ExtractionInvalid`, preserving the raw response, if the retry also
    fails.

    `validate` receives `(data, is_last_attempt)`. The explicit flag
    matters: a caller that wants to behave differently on the final
    attempt (T3.41 -- degrade instead of raising) cannot reliably infer
    "is this the last attempt" from how many times it has been called,
    since `validate` is only invoked when a response actually parses as a
    JSON object. A first attempt that returns unparseable text never
    reaches `validate` at all, which would silently miscount if the
    caller tried to track attempt number itself.

    Returns `(result, cost_usd)` -- cost accumulated across both attempts
    if a retry happened, so callers get an honest total rather than just
    the winning attempt's cost.
    """

    def _attempt(
        active_prompt: str, is_last_attempt: bool
    ) -> tuple[T | None, str | None, str, float]:
        response = client.complete(image, active_prompt, schema=schema)
        if not isinstance(response.parsed_json, dict):
            return None, "response was not a JSON object", response.raw_text, response.cost_usd
        try:
            result = validate(response.parsed_json, is_last_attempt)
            return result, None, response.raw_text, response.cost_usd
        except (ValueError, PydanticValidationError) as exc:
            return None, str(exc), response.raw_text, response.cost_usd

    result, error, raw_text, cost = _attempt(prompt, is_last_attempt=False)
    if error is None:
        return result, cost  # type: ignore[return-value]

    repair_prompt = (
        f"{prompt}\n\n"
        "Your previous response failed validation with this error:\n"
        f"{error}\n\n"
        "Please respond again, correcting the error. Respond with JSON only."
    )
    result, error, raw_text, retry_cost = _attempt(repair_prompt, is_last_attempt=True)
    total_cost = cost + retry_cost
    if error is None:
        return result, total_cost  # type: ignore[return-value]

    raise ExtractionInvalid(
        f"Extraction failed validation after one repair retry: {error}",
        raw_response=raw_text,
    )
