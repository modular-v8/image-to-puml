"""T2.21 phase gate: run the full corpus end to end, score each diagram
against its ground-truth IR, and produce the baseline scorecard. Not part
of the shipped package -- a one-off runner for this specific gate."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"'))

from umlregen.config import DEFAULT_EVAL_MODEL_ID
from umlregen.eval.report import (
    aggregate_scores,
    append_failure_log,
    append_run_log,
    classify_failure,
    format_failure_breakdown,
    format_scorecard,
)
from umlregen.eval.score import score
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

print("model:", DEFAULT_EVAL_MODEL_ID)

ir_dir = Path("corpus/ir")
img_dir = Path("corpus/img")

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None

raw_client = OpenRouterClient(model_id=DEFAULT_EVAL_MODEL_ID, timeout=90.0, requests_per_minute=40.0)
client = CachedVisionClient(raw_client, model_id=DEFAULT_EVAL_MODEL_ID, cache_dir=Path(".cache"))

results = []
per_diagram = []
failures = []  # T4.20: (diagram_name, mode) pairs for the taxonomy breakdown

for ir_path in sorted(ir_dir.glob("*.json")):
    name = ir_path.stem
    img_path = _find_image(img_dir, name)
    if img_path is None:
        print(f"SKIP {name}: no rendered image found")
        continue

    expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
    image_bytes = img_path.read_bytes()

    started = time.monotonic()
    try:
        # T4.19: extract_classes no longer returns an empty class list --
        # it either returns classes or raises ExtractionDeclined.
        stage_a, cost_a = extract_classes(client, image_bytes)
        actual, cost_b = extract_relationships(client, image_bytes, stage_a)
    except Exception as exc:  # noqa: BLE001 -- baseline runner, not shipped code
        mode = classify_failure(exc)
        print(f"{name}: FAILED [{mode}] {type(exc).__name__}: {exc}")
        failures.append((name, mode))
        append_failure_log(diagram_name=name, model_id=DEFAULT_EVAL_MODEL_ID, mode=mode, message=str(exc))
        continue
    latency = time.monotonic() - started

    diagram_score = score(expected, actual)
    cost = cost_a + cost_b
    results.append(diagram_score)
    per_diagram.append((name, diagram_score, cost, latency, len(actual.warnings)))

    print(
        f"{name}: class_recall={diagram_score.class_recall:.0%} "
        f"rel_f1={diagram_score.relationship_f1:.0%} "
        f"pair_recall={diagram_score.pair_recall:.0%} "
        f"kind_acc={diagram_score.kind_accuracy_given_correct_pair:.0%} "
        f"cost=${cost:.4f} warnings={len(actual.warnings)}"
    )

print()
print("=" * 70)
aggregated = aggregate_scores(results)
print(format_scorecard(aggregated, title=f"Baseline scorecard ({len(results)} diagrams)"))

total_cost = sum(c for _, _, c, _, _ in per_diagram)
total_latency = sum(latency for _, _, _, latency, _ in per_diagram)
total_warnings = sum(w for _, _, _, _, w in per_diagram)
costs_sorted = sorted(c for _, _, c, _, _ in per_diagram)
median_cost = costs_sorted[len(costs_sorted) // 2] if costs_sorted else 0.0

print(f"\nTotal cost: ${total_cost:.4f} | Median cost/diagram: ${median_cost:.4f}")
print(f"Total warnings: {total_warnings}")

if failures:
    print()
    print(format_failure_breakdown(failures, title="Corpus failure breakdown"))

append_run_log(
    aggregated,
    model_id=DEFAULT_EVAL_MODEL_ID,
    cost_usd=total_cost,
    latency_seconds=total_latency,
    warning_count=total_warnings,
)
print("\nAppended to runs/run_log.jsonl")
