"""`VisionClient` backed by the Claude Agent SDK, so calls draw on the
user's logged-in Claude Code (Pro/Max) account instead of a metered API
key. Optional: `uv sync --extra claude`. If `ANTHROPIC_API_KEY` is set in
the environment, the Claude Code CLI uses it and bills the API instead.

The SDK drives the `claude` CLI as a subprocess. It is locked down to a
plain single-turn vision answer: no built-in tools, no settings files,
no thinking.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from umlregen.errors import DependencyMissing, ProviderAuthError, ProviderRateLimited, UmlRegenError
from umlregen.perception.client import VisionResponse

CLAUDE_MODEL_PREFIX = "claude-"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMITED = 429

_SYSTEM_PROMPT = "You read UML diagrams from images. Follow the user's output instructions exactly."
_INSTALL_HINT = "Install the Claude Agent SDK with `uv sync --extra claude`, and make sure the `claude` CLI is logged in."


def _mime(image: bytes) -> str:
    return "image/png" if image.startswith(_PNG_MAGIC) else "image/jpeg"


def _parse_json(text: str) -> Any:
    """Shallow parse, tolerating a markdown code fence; the real repair
    lives in extract.py."""
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


class ClaudeAgentClient:
    """`schema` is ignored: the pipeline's prompts already embed it, and
    its repair-retry covers a response that strays from it."""

    def __init__(self, *, model_id: str) -> None:
        self._model_id = model_id

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        # One short-lived event loop per call: callers are sync, and may be
        # worker threads with no loop of their own.
        return asyncio.run(self._complete_async(image, prompt))

    async def _complete_async(self, image: bytes, prompt: str) -> VisionResponse:
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                CLINotFoundError,
                ClaudeSDKError,
                ResultError,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as exc:
            raise DependencyMissing(f"claude-agent-sdk is not installed. {_INSTALL_HINT}") from exc

        options = ClaudeAgentOptions(
            model=self._model_id,
            system_prompt=_SYSTEM_PROMPT,
            tools=[],
            setting_sources=[],
            max_turns=1,
            thinking={"type": "disabled"},
        )

        async def one_message():  # noqa: ANN202
            yield {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": _mime(image),
                                "data": base64.b64encode(image).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
                "parent_tool_use_id": None,
            }

        texts: list[str] = []
        result: ResultMessage | None = None
        try:
            async for message in query(prompt=one_message(), options=options):
                if isinstance(message, AssistantMessage):
                    texts.extend(b.text for b in message.content if isinstance(b, TextBlock))
                if isinstance(message, ResultMessage):
                    result = message
        except CLINotFoundError as exc:
            raise DependencyMissing(f"The `claude` CLI was not found. {_INSTALL_HINT}") from exc
        except ResultError as exc:
            # e.g. an unknown model id: the CLI reports it as an error result.
            self._raise_error(exc, fallback=str(exc))
        except ClaudeSDKError as exc:
            raise UmlRegenError(f"Claude Agent SDK error for model {self._model_id!r}: {exc}") from exc

        if result is None:
            raise UmlRegenError("Claude Agent SDK returned no result.")
        if result.is_error:
            self._raise_error(result, fallback=result.subtype)

        raw_text = result.result if result.result is not None else "".join(texts)
        usage = result.usage or {}
        return VisionResponse(
            raw_text=raw_text,
            parsed_json=_parse_json(raw_text),
            model_id=self._model_id,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            cost_usd=result.total_cost_usd or 0.0,
            finish_reason=result.stop_reason,
        )

    def _raise_error(self, result: Any, *, fallback: str) -> None:
        """`result` is a `ResultMessage` or a `ResultError`; both carry
        errors, result text and api_error_status."""
        detail = "; ".join(result.errors or []) or result.result or fallback
        if result.api_error_status in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
            raise ProviderAuthError(
                f"Claude rejected the request ({result.api_error_status}). Log in with `claude` and retry."
            )
        if result.api_error_status == _HTTP_RATE_LIMITED:
            raise ProviderRateLimited(
                f"Claude rate-limited model {self._model_id!r} (429); your plan's usage limit may be "
                "reached. Retry later."
            )
        raise UmlRegenError(f"Claude Agent SDK error for model {self._model_id!r}: {detail}")
