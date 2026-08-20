"""T3.28 ceiling experiment: run both the corpus and the holdout through a
frontier vision model, using the existing harness unchanged -- no prompt
edits, no config changes beyond the model ID. Mirrors run_baseline.py and
run_holdout.py exactly (same extraction calls, same scorer); the only
difference is the model ID and that this script covers both sets in one
run so they share one recorded date. Not part of the shipped package --
a one-off runner for this specific gate."""

import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"'))

from umlregen.eval.report import aggregate_scores, append_run_log, format_scorecard
from umlregen.eval.score import score
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

CEILING_MODEL_ID = "google/gemini-3.1-pro-preview"

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def run_set(*, name: str, ir_dir: Path, img_dir: Path, client) -> tuple[list, list]:
    results = []
    per_diagram = []

    for ir_path in sorted(ir_dir.glob("*.json")):
        diagram_name = ir_path.stem
        img_path = _find_image(img_dir, diagram_name)
        if img_path is None:
            print(f"{name}/{diagram_name}: SKIP -- no rendered image found")
            continue

        expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        image_bytes = img_path.read_bytes()

        started = time.monotonic()
        try:
            stage_a, cost_a = extract_classes(client, image_bytes)
            if not stage_a.classes:
                print(f"{name}/{diagram_name}: NO CLASSES FOUND, skipping")
                continue
            actual, cost_b = extract_relationships(client, image_bytes, stage_a)
        except Exception as exc:  # noqa: BLE001 -- ceiling runner, not shipped code
            print(f"{name}/{diagram_name}: ERROR {type(exc).__name__}: {exc}")
            continue
        latency = time.monotonic() - started

        diagram_score = score(expected, actual)
        cost = cost_a + cost_b
        results.append(diagram_score)
        per_diagram.append((diagram_name, diagram_score, cost, latency, len(actual.warnings)))

        print(
            f"{name}/{diagram_name}: class_recall={diagram_score.class_recall:.0%} "
            f"member_f1={diagram_score.member_f1:.0%} "
            f"rel_f1={diagram_score.relationship_f1:.0%} "
            f"pair_recall={diagram_score.pair_recall:.0%} "
            f"kind_acc={diagram_score.kind_accuracy_given_correct_pair:.0%} "
            f"cost=${cost:.4f} warnings={len(actual.warnings)}"
        )

    return results, per_diagram


def main() -> None:
    print("model:", CEILING_MODEL_ID)
    print("date:", date.today().isoformat())

    raw_client = OpenRouterClient(model_id=CEILING_MODEL_ID, timeout=120.0, requests_per_minute=40.0)
    client = CachedVisionClient(raw_client, model_id=CEILING_MODEL_ID, cache_dir=Path(".cache"))

    grand_total_cost = 0.0
    grand_total_latency = 0.0

    for set_name, ir_dir, img_dir in (
        ("corpus", Path("corpus/ir"), Path("corpus/img")),
        ("holdout", Path("corpus/holdout/ir"), Path("corpus/holdout/img")),
    ):
        print()
        print("=" * 70)
        print(f"Running {set_name} against {CEILING_MODEL_ID}")
        print("=" * 70)

        results, per_diagram = run_set(name=set_name, ir_dir=ir_dir, img_dir=img_dir, client=client)

        if not results:
            print(f"\n{set_name}: no diagrams scored")
            continue

        aggregated = aggregate_scores(results)
        print()
        print(format_scorecard(aggregated, title=f"{set_name.capitalize()} scorecard ({len(results)} diagrams)"))

        total_cost = sum(c for _, _, c, _, _ in per_diagram)
        total_latency = sum(latency for _, _, _, latency, _ in per_diagram)
        total_warnings = sum(w for _, _, _, _, w in per_diagram)
        grand_total_cost += total_cost
        grand_total_latency += total_latency

        print(f"\n{set_name} total cost: ${total_cost:.4f}")
        print(f"{set_name} total warnings: {total_warnings}")

        append_run_log(
            aggregated,
            model_id=CEILING_MODEL_ID,
            cost_usd=total_cost,
            latency_seconds=total_latency,
            warning_count=total_warnings,
        )

    print()
    print("=" * 70)
    print(f"Grand total cost (corpus + holdout): ${grand_total_cost:.4f}")
    print(f"Grand total latency: {grand_total_latency:.1f}s")
    print("\nAppended to runs/run_log.jsonl (one row per set)")


if __name__ == "__main__":
    main()
