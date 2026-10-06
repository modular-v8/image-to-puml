"""`serve` wiring, offline: uvicorn and the client are monkeypatched, so
nothing binds a port, touches the network, or needs an API key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from umlregen import cli
from umlregen.perception.claude_agent import ClaudeAgentClient
from umlregen.perception.cache import CachedVisionClient

runner = CliRunner()


class _NullClient:
    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> Any:
        raise AssertionError("serve must not call the model at startup")


@pytest.fixture
def built_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(cli, "_STATIC_DIR", tmp_path)
    return tmp_path


def test_serve_binds_loopback_on_given_port(built_static: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "_build_client", lambda *a, **k: _NullClient())
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    result = runner.invoke(cli.app, ["serve", "--port", "9123"])

    assert result.exit_code == 0
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 9123
    assert "http://127.0.0.1:9123" in result.output


def test_serve_forces_fresh_calls(built_static: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_build(*args: Any, **kwargs: Any) -> _NullClient:
        seen.update(kwargs)
        return _NullClient()

    monkeypatch.setattr(cli, "_build_client", fake_build)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: None)

    runner.invoke(cli.app, ["serve"])

    assert seen["force_refresh"] is True


def test_serve_fails_with_build_hint_when_ui_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_STATIC_DIR", tmp_path)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("must not start"))

    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code != 0
    assert "pnpm" in result.output


def test_claude_model_ids_use_the_agent_sdk_client(tmp_path: Path) -> None:
    client = cli._build_client("claude-opus-5-5", tmp_path, 20.0, force_refresh=True)

    assert isinstance(client, CachedVisionClient)
    assert isinstance(client._wrapped, ClaudeAgentClient)
