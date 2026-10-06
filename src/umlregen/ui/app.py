"""The UI's FastAPI app. Endpoints only adapt HTTP to existing functions
(`validate_image`, `regenerate`, `build_review`, `render`) -- no pipeline
logic lives here.

    browser -> POST /api/regenerate -> upload guard -> validate_image
                                    -> regenerate (one at a time)
                                    -> build_review + render(svg)
            -> POST /api/render     -> render(svg)   (no model call)
            -> GET  /api/info       -> model badge + toolchain status
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from umlregen.api import regenerate
from umlregen.config import Config
from umlregen.errors import (
    DependencyMissing,
    ExtractionInvalid,
    InvalidImage,
    NoClassesFound,
    ProviderAuthError,
    ProviderRateLimited,
    RenderFailed,
    RepetitionDetected,
    ResponseTruncated,
    UmlRegenError,
)
from umlregen.generate.review import build_review, flagged_items
from umlregen.input_validation import validate_image
from umlregen.perception.client import VisionClient
from umlregen.render.plantuml import preflight, render
from umlregen.ui.models import (
    InfoResponse,
    RegenerateResponse,
    RenderRequest,
    RenderResponse,
    Review,
)

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8765

_BYTES_PER_MB = 1024 * 1024
MAX_UPLOAD_BYTES = 20 * _BYTES_PER_MB
_UPLOAD_CHUNK_BYTES = _BYTES_PER_MB
# Multipart framing around the file itself; keeps a file of exactly
# MAX_UPLOAD_BYTES from being refused by the Content-Length pre-check.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024

_HTTP_BAD_REQUEST = 400
_HTTP_BUSY = 409
_HTTP_TOO_LARGE = 413
_HTTP_UNPROCESSABLE = 422
_HTTP_RATE_LIMITED = 429
_HTTP_SERVER_ERROR = 500
_HTTP_BAD_GATEWAY = 502
_HTTP_UNAVAILABLE = 503

_REGENERATE_PATH = "/api/regenerate"
_FREE_MODEL_SUFFIX = ":free"

# Exception classes are siblings under UmlRegenError, so order is free.
_ERROR_MAP: tuple[tuple[type[UmlRegenError], int, str], ...] = (
    (InvalidImage, _HTTP_BAD_REQUEST, "invalid_image"),
    (NoClassesFound, _HTTP_UNPROCESSABLE, "no_classes"),
    (ProviderRateLimited, _HTTP_RATE_LIMITED, "rate_limited"),
    (ProviderAuthError, _HTTP_BAD_GATEWAY, "provider_auth"),
    (ResponseTruncated, _HTTP_BAD_GATEWAY, "extraction_failed"),
    (RepetitionDetected, _HTTP_BAD_GATEWAY, "extraction_failed"),
    (ExtractionInvalid, _HTTP_BAD_GATEWAY, "extraction_failed"),
    (RenderFailed, _HTTP_UNPROCESSABLE, "render_failed"),
    (DependencyMissing, _HTTP_UNAVAILABLE, "render_unavailable"),
)


class _ApiError(Exception):
    def __init__(self, status: int, kind: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.message = message


def _error_response(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"kind": kind, "message": message})


def _too_large_message() -> str:
    return f"Image exceeds the {MAX_UPLOAD_BYTES // _BYTES_PER_MB} MB upload limit."


def _describe(exc: UmlRegenError) -> str:
    """A `RenderFailed` message alone ("exit code 1") hides what the user
    needs to fix their PUML; append PlantUML's own stderr."""
    if isinstance(exc, RenderFailed) and exc.stderr.strip():
        return f"{exc}\n{exc.stderr.strip()}"
    return str(exc)


def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Copies the upload to `dest` in chunks, aborting past the byte cap
    so an oversized (or chunked, length-less) body is never held whole."""
    written = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(_UPLOAD_CHUNK_BYTES):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise _ApiError(_HTTP_TOO_LARGE, "too_large", _too_large_message())
            out.write(chunk)


def _render_svg(puml: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = render(puml, "svg", Path(tmp) / "diagram.svg")
        return out.read_text(encoding="utf-8")


def create_app(config: Config, client: VisionClient, static_dir: Path | None = None) -> FastAPI:
    """`client` is injected so tests run on a `FakeVisionClient` with no
    network and no key. `static_dir` is the built frontend; omitted, only
    the API is served."""
    app = FastAPI(title="uml-regen", docs_url="/docs")
    run_lock = threading.Lock()

    @app.middleware("http")
    async def _reject_oversized(request: Request, call_next):  # noqa: ANN001, ANN202
        # Refuses on the declared length before the body is parsed or spooled.
        declared = request.headers.get("content-length", "")
        too_big = declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES
        if request.url.path == _REGENERATE_PATH and too_big:
            return _error_response(_HTTP_TOO_LARGE, "too_large", _too_large_message())
        return await call_next(request)

    @app.exception_handler(_ApiError)
    async def _on_api_error(_: Request, exc: _ApiError) -> JSONResponse:
        return _error_response(exc.status, exc.kind, exc.message)

    @app.exception_handler(UmlRegenError)
    async def _on_domain_error(_: Request, exc: UmlRegenError) -> JSONResponse:
        for error_type, status, kind in _ERROR_MAP:
            if isinstance(exc, error_type):
                return _error_response(status, kind, _describe(exc))
        return _error_response(_HTTP_SERVER_ERROR, "error", _describe(exc))

    @app.exception_handler(Exception)
    async def _on_unexpected(_: Request, __: Exception) -> JSONResponse:
        # Deliberately generic: an arbitrary exception's text is not
        # known to be free of secrets.
        return _error_response(_HTTP_SERVER_ERROR, "error", "Unexpected server error.")

    @app.get("/api/info", response_model=InfoResponse)
    def info() -> InfoResponse:
        missing: str | None = None
        try:
            preflight()
        except DependencyMissing as exc:
            missing = str(exc)

        return InfoResponse(
            model_id=config.model_id,
            is_free=config.model_id.endswith(_FREE_MODEL_SUFFIX),
            render_available=missing is None,
            render_missing=missing,
        )

    @app.post(_REGENERATE_PATH, response_model=RegenerateResponse)
    def regenerate_endpoint(image: UploadFile = File(...)) -> RegenerateResponse:
        if not run_lock.acquire(blocking=False):
            raise _ApiError(_HTTP_BUSY, "busy", "A regeneration is already running.")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                image_path = Path(tmp) / "upload"
                _save_upload(image, image_path)
                image_bytes = validate_image(image_path)

            result = regenerate(image_bytes, config, client=client)
        finally:
            run_lock.release()

        # A missing or failing render is not a failed run: the PUML is
        # the deliverable, the SVG a convenience.
        svg: str | None = None
        render_error: str | None = None
        try:
            svg = _render_svg(result.puml)
        except UmlRegenError as exc:
            render_error = _describe(exc)

        return RegenerateResponse(
            puml=result.puml,
            svg=svg,
            render_error=render_error,
            review_md=build_review(result.diagram, config.confidence_threshold),
            review=Review(
                threshold=config.confidence_threshold,
                items=flagged_items(result.diagram, config.confidence_threshold),
            ),
            warnings=result.warnings,
            model_id=result.model_id,
            cost_usd=result.cost_usd,
            latency_seconds=result.latency_seconds,
            class_count=len(result.diagram.classes),
            relationship_count=len(result.diagram.relationships),
        )

    @app.post("/api/render", response_model=RenderResponse)
    def render_endpoint(body: RenderRequest) -> RenderResponse:
        return RenderResponse(svg=_render_svg(body.puml))

    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
