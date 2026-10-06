"""Offline tests for the UI's HTTP layer. A scripted `VisionClient` stands
in for the provider, so no network and no API key are involved; every
rejection case also asserts the client was never called.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from umlregen.config import Config
from umlregen.errors import (
    DependencyMissing,
    ProviderAuthError,
    ProviderRateLimited,
    UmlRegenError,
)
from umlregen.perception.client import VisionResponse
from umlregen.ui import app as ui_app
from umlregen.ui.app import MAX_UPLOAD_BYTES, create_app

from _toolchain import requires_render_toolchain

_STAGE_A_TWO_CLASSES = {
    "classes": [
        {"name": "Foo", "kind": "class", "attributes": [], "methods": []},
        {"name": "Bar", "kind": "class", "attributes": [], "methods": []},
    ],
    "relationships": [],
}
_STAGE_A_EMPTY = {"classes": [], "relationships": []}
_STAGE_B_ONE_RELATIONSHIP = {
    "relationships": [{"source": "Foo", "target": "Bar", "kind": "association", "evidence": "solid line"}]
}

_KEY_SENTINEL = "sk-or-SENTINEL-must-never-appear"
_VALID_PUML = "@startuml\nclass Foo\nclass Bar\nFoo --> Bar\n@enduml\n"
_BROKEN_PUML = "@startuml\nclass {{{ nope\n@enduml\n"


def _response(parsed: dict[str, Any]) -> VisionResponse:
    return VisionResponse(raw_text="ok", parsed_json=parsed, model_id="test/model")


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        self.calls += 1
        return self._responses.pop(0)


class _RaisingClient:
    def __init__(self, exc: UmlRegenError) -> None:
        self._exc = exc
        self.calls = 0

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        self.calls += 1
        raise self._exc


class _BlockingClient:
    """Holds the first call open until `release` is set."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        self.entered.set()
        self.release.wait(timeout=10)
        return _response(_STAGE_A_TWO_CLASSES)


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    return buf.getvalue()


def _gif_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("P", (4, 4)).save(buf, format="GIF")
    return buf.getvalue()


def _upload(client: TestClient, data: bytes, name: str = "diagram.png"):
    return client.post("/api/regenerate", files={"image": (name, data, "image/png")})


def _app_client(vision: Any, config: Config | None = None) -> TestClient:
    app = create_app(config or Config(), vision)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _sentinel_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _KEY_SENTINEL)


def test_info_free_default() -> None:
    body = _app_client(_ScriptedClient([])).get("/api/info").json()

    assert body["model_id"] == Config().model_id
    assert body["is_free"] is True


def test_info_paid_model() -> None:
    paid = Config(model_id="google/gemma-4-26b-a4b-it")

    assert _app_client(_ScriptedClient([]), paid).get("/api/info").json()["is_free"] is False


def test_info_reflects_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> dict[str, str]:
        raise DependencyMissing("Required tool 'java' was not found")

    monkeypatch.setattr(ui_app, "preflight", missing)
    body = _app_client(_ScriptedClient([])).get("/api/info").json()

    assert body["render_available"] is False
    assert "java" in body["render_missing"]


def test_regenerate_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui_app, "_render_svg", lambda puml: "<svg/>")
    vision = _ScriptedClient([_response(_STAGE_A_TWO_CLASSES), _response(_STAGE_B_ONE_RELATIONSHIP)])

    res = _upload(_app_client(vision), _png_bytes())
    body = res.json()

    assert res.status_code == 200
    assert "Foo" in body["puml"]
    assert body["svg"] == "<svg/>"
    assert body["review_md"].startswith("# Review")
    assert (body["class_count"], body["relationship_count"]) == (2, 1)
    assert vision.calls == 2


def test_review_matches_review_md(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui_app, "_render_svg", lambda puml: "<svg/>")
    evidence = "<b>x</b> and **y** and `z`"
    stage_b = {
        "relationships": [
            {"source": "Foo", "target": "Bar", "kind": "association", "evidence": evidence},
        ]
    }
    vision = _ScriptedClient([_response(_STAGE_A_TWO_CLASSES), _response(stage_b)])
    # The placeholder confidence (0.5) sits below this threshold, so it is flagged.
    flagged_config = Config(confidence_threshold=0.9)

    body = _upload(_app_client(vision, flagged_config), _png_bytes()).json()
    review, review_md = body["review"], body["review_md"]

    assert review["threshold"] == 0.9
    assert len(review["items"]) == 1
    item = review["items"][0]
    assert f"`.puml:{item['line']}`" in review_md
    assert f"`{item['source']} {item['kind']} {item['target']}`" in review_md
    assert f"confidence {item['confidence']:.2f}" in review_md
    assert item["evidence"] == evidence


def test_gif_rejected_without_a_model_call() -> None:
    vision = _ScriptedClient([])

    res = _upload(_app_client(vision), _gif_bytes())

    assert res.status_code == 400
    assert res.json()["kind"] == "invalid_image"
    assert vision.calls == 0


def test_text_renamed_png_rejected_without_a_model_call() -> None:
    vision = _ScriptedClient([])

    res = _upload(_app_client(vision), b"not an image at all", name="fake.png")

    assert res.status_code == 400
    assert vision.calls == 0


def test_oversized_upload_rejected_without_a_model_call() -> None:
    vision = _ScriptedClient([])

    res = _upload(_app_client(vision), b"\0" * (MAX_UPLOAD_BYTES + 1))

    assert res.status_code == 413
    assert res.json()["kind"] == "too_large"
    assert vision.calls == 0


def test_no_classes_is_422() -> None:
    vision = _ScriptedClient([_response(_STAGE_A_EMPTY), _response(_STAGE_A_EMPTY)])

    res = _upload(_app_client(vision), _png_bytes())

    assert res.status_code == 422
    assert res.json()["kind"] == "no_classes"


def test_rate_limit_is_429_with_original_message() -> None:
    message = "Rate limited. Try --model google/gemma-4-26b-a4b-it"
    res = _upload(_app_client(_RaisingClient(ProviderRateLimited(message))), _png_bytes())

    assert res.status_code == 429
    assert res.json() == {"kind": "rate_limited", "message": message}


def test_auth_error_is_502() -> None:
    res = _upload(_app_client(_RaisingClient(ProviderAuthError("key rejected"))), _png_bytes())

    assert res.status_code == 502
    assert res.json()["kind"] == "provider_auth"


def test_render_unavailable_does_not_fail_regenerate(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(puml: str, fmt: str, out: Path) -> Path:
        raise DependencyMissing("Required tool 'dot' was not found")

    monkeypatch.setattr(ui_app, "render", missing)
    vision = _ScriptedClient([_response(_STAGE_A_TWO_CLASSES), _response(_STAGE_B_ONE_RELATIONSHIP)])

    res = _upload(_app_client(vision), _png_bytes())
    body = res.json()

    assert res.status_code == 200
    assert body["svg"] is None
    assert "dot" in body["render_error"]
    assert "Foo" in body["puml"]


def test_second_regenerate_while_busy_is_409() -> None:
    vision = _BlockingClient()
    client = _app_client(vision)
    first: dict[str, Any] = {}

    def run_first() -> None:
        first["res"] = _upload(client, _png_bytes())

    thread = threading.Thread(target=run_first)
    thread.start()
    assert vision.entered.wait(timeout=10)

    second = _upload(client, _png_bytes())
    vision.release.set()
    thread.join(timeout=10)

    assert second.status_code == 409
    assert second.json()["kind"] == "busy"


@requires_render_toolchain
def test_render_valid_puml() -> None:
    vision = _ScriptedClient([])

    res = _app_client(vision).post("/api/render", json={"puml": _VALID_PUML})

    assert res.status_code == 200
    assert "<svg" in res.json()["svg"]
    assert vision.calls == 0


@requires_render_toolchain
def test_render_broken_puml_is_422_with_plantuml_error() -> None:
    res = _app_client(_ScriptedClient([])).post("/api/render", json={"puml": _BROKEN_PUML})

    assert res.status_code == 422
    assert res.json()["kind"] == "render_failed"


def test_render_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui_app, "_render_svg", lambda puml: "<svg/>")
    vision = _ScriptedClient([])

    _app_client(vision).post("/api/render", json={"puml": _VALID_PUML})

    assert vision.calls == 0


def test_render_rejects_oversized_puml() -> None:
    res = _app_client(_ScriptedClient([])).post("/api/render", json={"puml": "x" * 200_001})

    assert res.status_code == 422


def test_key_never_appears_in_any_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui_app, "_render_svg", lambda puml: "<svg/>")
    vision = _ScriptedClient([_response(_STAGE_A_TWO_CLASSES), _response(_STAGE_B_ONE_RELATIONSHIP)])
    client = _app_client(vision)

    responses = [
        client.get("/api/info"),
        _upload(client, _png_bytes()),
        _upload(client, _gif_bytes()),
        client.post("/api/render", json={"puml": _VALID_PUML}),
        client.get("/openapi.json"),
    ]

    assert all(_KEY_SENTINEL not in r.text for r in responses)


def test_root_serves_index_html(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>hello</html>", encoding="utf-8")
    app = create_app(Config(), _ScriptedClient([]), static_dir=tmp_path)

    res = TestClient(app).get("/")

    assert res.status_code == 200
    assert "hello" in res.text
