"""T3.35: characterize the noise floor. Runs the full corpus N=5 times,
cache disabled, identical prompts/config, under both the free default
model and its paid tier -- same model, so the only variable isolated is
free-tier vs paid-tier serving, not a model swap. Reports mean/min/max/
stddev per metric per model, and counts suspiciously short stage-A
responses per run. Not part of the shipped package -- a one-off
characterization run."""

import os
import statistics
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

from umlregen.eval.score import score
from umlregen.ir.models import Diagram
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

N_RUNS = 5
MODELS = {
    "free": "google/gemma-4-26b-a4b-it:free",
    "paid": "google/gemma-4-26b-a4b-it",
}
RATES = {"free": 8.0, "paid": 30.0}

METRICS = [
    "class_recall",
    "class_precision",
    "class_f1",
    "member_f1",
    "relationship_f1",
    "pair_recall",
    "kind_accuracy_given_correct_pair",
]

_SHORT_RESPONSE_CHAR_THRESHOLD = 300  # a real multi-class stage-A response is longer than this

ir_dir = Path("corpus/ir")
img_dir = Path("corpus/img")

diagrams = []
for ir_path in sorted(ir_dir.glob("*.json")):
    name = ir_path.stem
    img_path = img_dir / f"{name}.png"
    if not img_path.is_file():
        continue
    expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
    diagrams.append((name, expected, img_path.read_bytes()))

print(f"corpus: {len(diagrams)} diagrams, {N_RUNS} runs per model, cache disabled\n")

results: dict[str, list[dict[str, float]]] = {"free": [], "paid": []}
short_response_counts: dict[str, list[int]] = {"free": [], "paid": []}
total_cost: dict[str, float] = {"free": 0.0, "paid": 0.0}

for model_key, model_id in MODELS.items():
    print(f"=== {model_key}: {model_id} ===")
    client = OpenRouterClient(model_id=model_id, timeout=90.0, requests_per_minute=RATES[model_key])

    for run_idx in range(1, N_RUNS + 1):
        per_diagram_scores = []
        short_count = 0
        started = time.monotonic()
        for name, expected, image_bytes in diagrams:
            try:
                response_len_a = None
                stage_a, cost_a = extract_classes(client, image_bytes)
                if not stage_a.classes:
                    short_count += 1
                    continue
                if len(stage_a.classes) < len(expected.classes):
                    short_count += 1
                actual, cost_b = extract_relationships(client, image_bytes, stage_a)
            except Exception as exc:  # noqa: BLE001 -- characterization runner, not shipped code
                print(f"  run {run_idx} {name}: ERROR {type(exc).__name__}: {exc}")
                short_count += 1
                continue
            total_cost[model_key] += cost_a + cost_b
            per_diagram_scores.append(score(expected, actual))

        if not per_diagram_scores:
            print(f"  run {run_idx}: no scoreable diagrams, skipping")
            continue

        run_aggregate = {
            metric: statistics.mean(getattr(s, metric) for s in per_diagram_scores)
            for metric in METRICS
        }
        results[model_key].append(run_aggregate)
        short_response_counts[model_key].append(short_count)
        elapsed = time.monotonic() - started
        print(
            f"  run {run_idx}: class_recall={run_aggregate['class_recall']:.1%} "
            f"member_f1={run_aggregate['member_f1']:.1%} "
            f"rel_f1={run_aggregate['relationship_f1']:.1%} "
            f"kind_acc={run_aggregate['kind_accuracy_given_correct_pair']:.1%} "
            f"short_responses={short_count} elapsed={elapsed:.0f}s"
        )
    print()

print("=" * 78)
print("Noise floor -- mean / min / max / stddev across 5 runs, per model")
print("=" * 78)
for model_key, model_id in MODELS.items():
    runs = results[model_key]
    if not runs:
        print(f"\n{model_key} ({model_id}): no data")
        continue
    print(f"\n{model_key} ({model_id}), {len(runs)} runs, total cost ${total_cost[model_key]:.4f}")
    print(f"  short/incomplete stage-A responses per run: {short_response_counts[model_key]}")
    for metric in METRICS:
        values = [r[metric] for r in runs]
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        print(
            f"  {metric:38s} mean={mean:6.1%} min={min(values):6.1%} "
            f"max={max(values):6.1%} stddev={stdev:6.1%}"
        )

print("\nTotal cost across both models: ${:.4f}".format(total_cost["free"] + total_cost["paid"]))
