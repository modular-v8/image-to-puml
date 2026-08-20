"""Offline tests for OpenRouterClient's provider-failure mapping (T2.4):
401 -> ProviderAuthError (key never echoed), 429 -> ProviderRateLimited
after exponential backoff retries, transport/timeout -> retried then
re-raised as-is. All mocked via monkeypatched httpx.Client.post -- no
network access."""

import time

import httpx
import pytest

from umlregen.errors import ProviderAuthError, ProviderRateLimited
from umlregen.perception.openrouter import OpenRouterClient

_URL = "https://openrouter.ai/api/v1/chat/completions"

_SUCCESS_BODY = {
    "model": "test/model:free",
    "choices": [{"message": {"content": '{"ok": true}'}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001},
}


def _client() -> OpenRouterClient:
    # requests_per_minute=0 disables proactive throttling so these tests
    # run fast; the throttle itself is covered by test_openrouter_throttle.py.
    return OpenRouterClient(
        model_id="test/model:free",
        api_key="fake-key-for-offline-test",
        requests_per_minute=0,
    )


def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", _URL)
    return httpx.Response(status_code=status_code, json=json_body or {}, request=request)


def test_missing_api_key_raises_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderAuthError):
        OpenRouterClient(model_id="test/model:free", api_key=None)


def test_401_raises_provider_auth_error_without_echoing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: _response(401))
    client = _client()

    with pytest.raises(ProviderAuthError) as exc_info:
        client.complete(b"fake-image-bytes", "prompt")

    assert "fake-key-for-offline-test" not in str(exc_info.value)


def test_401_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_post(self, *a, **k):
        calls["n"] += 1
        return _response(401)

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = _client()

    with pytest.raises(ProviderAuthError):
        client.complete(b"fake-image-bytes", "prompt")

    assert calls["n"] == 1


def test_429_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_post(self, *a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            return _response(429)
        return _response(200, _SUCCESS_BODY)

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = _client()

    response = client.complete(b"fake-image-bytes", "prompt")

    assert calls["n"] == 2
    assert response.parsed_json == {"ok": True}


def test_429_exhausted_raises_provider_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: _response(429))
    client = _client()

    with pytest.raises(ProviderRateLimited, match="test/model:free"):
        client.complete(b"fake-image-bytes", "prompt")


def test_transport_error_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_post(self, *a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom", request=httpx.Request("POST", _URL))
        return _response(200, _SUCCESS_BODY)

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = _client()

    response = client.complete(b"fake-image-bytes", "prompt")

    assert calls["n"] == 2
    assert response.parsed_json == {"ok": True}


def test_200_with_embedded_error_raises_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    # Observed live from nvidia/nemotron-nano-12b-v2-vl:free during T2.6:
    # OpenRouter can return HTTP 200 with an embedded error object instead
    # of an HTTP error status, when the upstream model itself times out.
    body = {"error": {"message": "Upstream idle timeout exceeded", "code": 504}}
    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: _response(200, body))
    client = _client()

    with pytest.raises(RuntimeError, match="Upstream idle timeout exceeded"):
        client.complete(b"fake-image-bytes", "prompt")


def test_transport_error_exhausted_reraises_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_post(self, *a, **k):
        calls["n"] += 1
        raise httpx.ConnectError("boom", request=httpx.Request("POST", _URL))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = _client()

    with pytest.raises(httpx.ConnectError):
        client.complete(b"fake-image-bytes", "prompt")

    assert calls["n"] == 3
