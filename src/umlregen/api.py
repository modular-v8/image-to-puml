"""`regenerate(image, config) -> Result`: the single seam. The CLI, the
eval harness, and any future UI all go through this one function -- see
plan.md's Architecture.
"""

from __future__ import annotations

import time

from pydantic import BaseModel

from umlregen.config import Config
from umlregen.errors import ExtractionDeclined, NoClassesFound
from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.client import VisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient


# T4.13 / spec §requirements: "correctly process diagrams containing up
# to 15 classes and 25 relationships" -- beyond this, still process
# best-effort rather than refuse, but warn that accuracy isn't guaranteed
# past the tested bounds.
MAX_SUPPORTED_CLASSES = 15
MAX_SUPPORTED_RELATIONSHIPS = 25


class Result(BaseModel):
    """Everything one `regenerate()` call produces: the deliverable
    (`puml`), the IR that generated it, warnings accumulated along the
    way, and enough run metadata to feed the scorecard and run log."""

    puml: str
    diagram: Diagram
    warnings: list[str]
    model_id: str
    cost_usd: float
    latency_seconds: float


def _default_client(config: Config) -> VisionClient:
    raw = OpenRouterClient(
        model_id=config.model_id,
        requests_per_minute=config.requests_per_minute,
        repetition_retry_attempts=config.repetition_retry_attempts,
    )
    return CachedVisionClient(raw, model_id=config.model_id, cache_dir=config.cache_dir)


def regenerate(image: bytes, config: Config, *, client: VisionClient | None = None) -> Result:
    """Runs the full pipeline: stage A -> stage B -> `.puml` generation.

    `client` is injectable (a `FakeVisionClient` for offline tests, or a
    shared client the eval harness reuses across a corpus run) and
    defaults to a fresh cached `OpenRouterClient` built from `config`.

    Raises `NoClassesFound` if stage A finds no classes at all, rather
    than reporting an empty `.puml` as a success. T4.19: `extract_classes`
    itself now distinguishes *why* -- a genuine model decline raises the
    more specific `ExtractionDeclined` -- but `regenerate()`'s own public
    contract stays `NoClassesFound` regardless of cause; the finer-grained
    distinction is for the eval harness's failure taxonomy (T4.20), not
    for callers of this function.
    """
    active_client = client if client is not None else _default_client(config)

    started_at = time.monotonic()

    try:
        stage_a_diagram, stage_a_cost = extract_classes(active_client, image)
    except ExtractionDeclined as exc:
        raise NoClassesFound("No classes were found in the image -- not a class diagram?") from exc

    full_diagram, stage_b_cost = extract_relationships(active_client, image, stage_a_diagram)

    # T4.13: degradation, not refusal -- both cases still produce a
    # diagram, just flagged so the CLI/library caller knows to look twice.
    if full_diagram.classes and not full_diagram.relationships:
        full_diagram.warnings.append("No relationships were found between the extracted classes.")

    if len(full_diagram.classes) > MAX_SUPPORTED_CLASSES or len(full_diagram.relationships) > MAX_SUPPORTED_RELATIONSHIPS:
        full_diagram.warnings.append(
            f"Diagram has {len(full_diagram.classes)} classes and {len(full_diagram.relationships)} "
            f"relationships, exceeding the supported bounds ({MAX_SUPPORTED_CLASSES} classes / "
            f"{MAX_SUPPORTED_RELATIONSHIPS} relationships) -- processed best-effort; accuracy beyond "
            "this size has not been measured."
        )

    puml_text = ir_to_puml(full_diagram, model_id=config.model_id)
    latency = time.monotonic() - started_at

    return Result(
        puml=puml_text,
        diagram=full_diagram,
        warnings=list(full_diagram.warnings),
        model_id=config.model_id,
        cost_usd=stage_a_cost + stage_b_cost,
        latency_seconds=latency,
    )
