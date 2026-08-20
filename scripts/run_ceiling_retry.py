"""T3.28 supplemental: retries exactly the two diagrams whose ceiling-run
stage-B call was confirmed truncated at the 4096-token cap (library_system,
visitor_pattern), with max_tokens raised. Stage A is untouched -- it's
still read from the same cache (already valid, non-truncated). Their
stale truncated stage-B cache entries were deleted first so this issues
genuinely fresh calls, not cache replays. Not part of the shipped
package -- a one-off, narrowly-scoped follow-up to run_ceiling.py."""

import os
import sys
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
from umlregen.errors import ExtractionInvalid
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

MODEL_ID = "google/gemini-3.1-pro-preview"
RAISED_MAX_TOKENS = 12000

raw_client = OpenRouterClient(
    model_id=MODEL_ID, timeout=180.0, requests_per_minute=40.0, max_completion_tokens=RAISED_MAX_TOKENS
)
client = CachedVisionClient(raw_client, model_id=MODEL_ID, cache_dir=Path(".cache"))

targets = [
    ("library_system", Path("corpus/ir/library_system.json"), Path("corpus/img/library_system.png")),
    ("visitor_pattern", Path("corpus/holdout/ir/visitor_pattern.json"), Path("corpus/holdout/img/visitor_pattern.png")),
]

total_cost = 0.0
for name, ir_path, img_path in targets:
    print(f"--- {name} (max_tokens={RAISED_MAX_TOKENS}) ---")
    expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
    image_bytes = img_path.read_bytes()

    stage_a, cost_a = extract_classes(client, image_bytes)
    print(f"  stage A: {len(stage_a.classes)} classes (cache), cost=${cost_a:.4f}")

    try:
        actual, cost_b = extract_relationships(client, image_bytes, stage_a)
    except ExtractionInvalid as exc:
        print(f"  stage B: STILL FAILED -- {exc}")
        continue

    cost = cost_a + cost_b
    total_cost += cost
    diagram_score = score(expected, actual)
    print(
        f"  stage B: {len(actual.relationships)} relationships, cost=${cost_b:.4f}, "
        f"warnings={actual.warnings}"
    )
    print(
        f"  scored: class_recall={diagram_score.class_recall:.0%} "
        f"member_f1={diagram_score.member_f1:.0%} "
        f"rel_f1={diagram_score.relationship_f1:.0%} "
        f"pair_recall={diagram_score.pair_recall:.0%} "
        f"kind_acc={diagram_score.kind_accuracy_given_correct_pair:.0%}"
    )
    print()

print(f"Total supplemental cost: ${total_cost:.4f}")
