"""T3.24: score --verify against --no-verify on both corpus and holdout.
For each diagram: extract a baseline diagram from the original image
(the --no-verify result), then run the verification loop starting from
that baseline (the --verify result) and score both against ground truth.
Not part of the shipped package -- a one-off comparison runner."""

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
from umlregen.eval.report import aggregate_scores, append_verify_log, format_scorecard
from umlregen.eval.score import score
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient
from umlregen.verify.loop import verify

print("model:", DEFAULT_EVAL_MODEL_ID)

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _run_set(name: str, ir_dir: Path, img_dir: Path, client, debug_root: Path):
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    baseline_scores = []
    verified_scores = []
    per_diagram = []

    for ir_path in sorted(ir_dir.glob("*.json")):
        diagram_name = ir_path.stem
        img_path = _find_image(img_dir, diagram_name)
        if img_path is None:
            print(f"SKIP {diagram_name}: no rendered image found")
            continue

        expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        image_bytes = img_path.read_bytes()

        try:
            stage_a, cost_a = extract_classes(client, image_bytes)
            if not stage_a.classes:
                print(f"{diagram_name}: NO CLASSES FOUND, skipping")
                continue
            baseline, cost_b = extract_relationships(client, image_bytes, stage_a)
        except Exception as exc:  # noqa: BLE001 -- comparison runner, not shipped code
            print(f"{diagram_name}: BASELINE ERROR {type(exc).__name__}: {exc}")
            continue
        baseline_cost = cost_a + cost_b

        baseline_score = score(expected, baseline)

        debug_dir = debug_root / diagram_name
        started = time.monotonic()
        try:
            verify_result = verify(baseline, client, max_rounds=2, debug_dir=debug_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"{diagram_name}: VERIFY ERROR {type(exc).__name__}: {exc}")
            continue
        verify_wall = time.monotonic() - started

        verified_score = score(expected, verify_result.diagram)

        baseline_scores.append(baseline_score)
        verified_scores.append(verified_score)
        per_diagram.append((diagram_name, baseline_score, verified_score, verify_result.stats, baseline_cost))

        append_verify_log(
            model_id=DEFAULT_EVAL_MODEL_ID,
            rounds_run=verify_result.stats.rounds_run,
            converged=verify_result.stats.converged,
            render_reextract_calls=verify_result.stats.render_reextract_calls,
            requery_calls=verify_result.stats.requery_calls,
            rejected_patch_count=len(verify_result.stats.rejected_patches),
            render_reextract_cost_usd=verify_result.stats.render_reextract_cost_usd,
            requery_cost_usd=verify_result.stats.requery_cost_usd,
            latency_seconds=verify_wall,
        )

        print(
            f"{diagram_name}: "
            f"kind_acc {baseline_score.kind_accuracy_given_correct_pair:.0%}->{verified_score.kind_accuracy_given_correct_pair:.0%} "
            f"rel_f1 {baseline_score.relationship_f1:.0%}->{verified_score.relationship_f1:.0%} "
            f"member_f1 {baseline_score.member_f1:.0%}->{verified_score.member_f1:.0%} "
            f"| verify: rounds={verify_result.stats.rounds_run} converged={verify_result.stats.converged} "
            f"calls={verify_result.stats.total_calls} rejected={len(verify_result.stats.rejected_patches)} "
            f"cost=${verify_result.stats.total_cost_usd:.4f}"
        )

    if not baseline_scores:
        print(f"{name}: no diagrams scored")
        return

    agg_baseline = aggregate_scores(baseline_scores)
    agg_verified = aggregate_scores(verified_scores)
    print()
    print(format_scorecard(agg_baseline, title=f"{name} -- baseline (--no-verify)"))
    print()
    print(format_scorecard(agg_verified, title=f"{name} -- verified (--verify)"))

    total_baseline_cost = sum(c for _, _, _, _, c in per_diagram)
    total_verify_cost = sum(s.total_cost_usd for _, _, _, s, _ in per_diagram)
    total_verify_calls = sum(s.total_calls for _, _, _, s, _ in per_diagram)
    print(f"\n{name} deltas (verified - baseline):")
    for field_name in agg_baseline.model_fields:
        delta = getattr(agg_verified, field_name) - getattr(agg_baseline, field_name)
        print(f"  {field_name:38s} {delta:+.1%}")
    print(
        f"\n{name} cost: baseline ${total_baseline_cost:.4f} + verify ${total_verify_cost:.4f} "
        f"(verify calls: {total_verify_calls}, avg {total_verify_calls / len(per_diagram):.1f}/diagram)"
    )


raw_client = OpenRouterClient(model_id=DEFAULT_EVAL_MODEL_ID, timeout=90.0, requests_per_minute=40.0)
client = CachedVisionClient(raw_client, model_id=DEFAULT_EVAL_MODEL_ID, cache_dir=Path(".cache"))

_run_set("Corpus", Path("corpus/ir"), Path("corpus/img"), client, Path("runs/verify_debug/corpus"))
_run_set("Holdout", Path("corpus/holdout/ir"), Path("corpus/holdout/img"), client, Path("runs/verify_debug/holdout"))

print("\nAppended per-diagram verify stats to runs/run_log.jsonl")
