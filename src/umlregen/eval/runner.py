"""Shared corpus-scoring loop: for every `(ir, image)` pair in a
directory, extract, score against ground truth, and classify failures by
T4.20's taxonomy. Factored out so `cli.py`'s `eval` subcommand and any
future caller share one implementation rather than each looping over the
directory by hand -- `scripts/run_baseline.py` and `run_holdout.py`
predate this and stay as their own one-off runners (not shipped code;
see their own docstrings), not retrofitted onto this for its own sake.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from umlregen.eval.report import classify_failure
from umlregen.eval.score import ScoreResult, score
from umlregen.ir.models import Diagram
from umlregen.perception.client import VisionClient
from umlregen.perception.extract import extract_classes, extract_relationships

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


@dataclass
class DiagramResult:
    name: str
    score: ScoreResult
    cost_usd: float
    latency_seconds: float
    warning_count: int


@dataclass
class EvalRunResult:
    scored: list[DiagramResult] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)  # (name, mode)
    skipped: list[str] = field(default_factory=list)  # no image found

    @property
    def total_cost_usd(self) -> float:
        return sum(d.cost_usd for d in self.scored)

    @property
    def total_latency_seconds(self) -> float:
        return sum(d.latency_seconds for d in self.scored)

    @property
    def total_warnings(self) -> int:
        return sum(d.warning_count for d in self.scored)


def run_eval_set(ir_dir: Path, img_dir: Path, client: VisionClient) -> EvalRunResult:
    """Runs extraction + scoring over every `ir_dir/*.json` with a
    matching image in `img_dir`, returning per-diagram results, a
    (name, mode) pair per failure, and any diagrams skipped for lacking a
    rendered image at all.
    """
    result = EvalRunResult()

    for ir_path in sorted(ir_dir.glob("*.json")):
        name = ir_path.stem
        img_path = _find_image(img_dir, name)
        if img_path is None:
            result.skipped.append(name)
            continue

        expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        image_bytes = img_path.read_bytes()

        started = time.monotonic()
        try:
            stage_a, cost_a = extract_classes(client, image_bytes)
            actual, cost_b = extract_relationships(client, image_bytes, stage_a)
        except Exception as exc:  # noqa: BLE001 -- classified below, not swallowed
            result.failures.append((name, classify_failure(exc)))
            continue
        latency = time.monotonic() - started

        result.scored.append(
            DiagramResult(
                name=name,
                score=score(expected, actual),
                cost_usd=cost_a + cost_b,
                latency_seconds=latency,
                warning_count=len(actual.warnings),
            )
        )

    return result
