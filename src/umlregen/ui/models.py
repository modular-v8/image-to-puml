"""Request/response contracts for the UI's JSON API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from umlregen.generate.review import ReviewItem

MAX_PUML_CHARS = 200_000


class InfoResponse(BaseModel):
    model_id: str
    is_free: bool
    render_available: bool
    render_missing: str | None = None


class Review(BaseModel):
    threshold: float
    items: list[ReviewItem]


class RegenerateResponse(BaseModel):
    puml: str
    svg: str | None = None
    render_error: str | None = None
    review_md: str
    review: Review
    warnings: list[str]
    model_id: str
    cost_usd: float
    latency_seconds: float
    class_count: int
    relationship_count: int


class RenderRequest(BaseModel):
    puml: str = Field(max_length=MAX_PUML_CHARS)


class RenderResponse(BaseModel):
    svg: str


class ErrorResponse(BaseModel):
    kind: str
    message: str
