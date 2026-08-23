"""One-off diagnostic for T5.9: dig into why media_library_icons and
observer_pattern score poorly on relationships in T5.4's full-coverage
holdout run. Replays both diagrams through the same cached client T5.4
used (cache warm from that run -- $0 marginal cost expected), then prints
the structural diff plus each actual relationship's model-reported
evidence, so the failure mode is visible rather than just the number.
Not part of the shipped package."""

import os
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"'))

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from umlregen.config import DEFAULT_EVAL_MODEL_ID
from umlregen.ir.diff import diff
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

raw_client = OpenRouterClient(model_id=DEFAULT_EVAL_MODEL_ID, timeout=90.0, requests_per_minute=40.0)
client = CachedVisionClient(raw_client, model_id=DEFAULT_EVAL_MODEL_ID, cache_dir=Path(".cache"))

TARGETS = [
    ("media_library_icons", Path("corpus/holdout/ir/media_library_icons.json"), Path("corpus/holdout/img/media_library_icons.png")),
    ("observer_pattern", Path("corpus/holdout/ir/observer_pattern.json"), Path("corpus/holdout/img/observer_pattern.jpg")),
]

for name, ir_path, img_path in TARGETS:
    print("=" * 70)
    print(name)
    print("=" * 70)

    expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
    image_bytes = img_path.read_bytes()

    stage_a, cost_a = extract_classes(client, image_bytes)
    actual, cost_b = extract_relationships(client, image_bytes, stage_a)
    print(f"cost this call: ${cost_a + cost_b:.4f} (should be ~$0 if cache is warm from T5.4)")

    id_to_name_expected = {c.id: c.name for c in expected.classes}
    id_to_name_actual = {c.id: c.name for c in actual.classes}

    print("\n--- expected relationships ---")
    for r in expected.relationships:
        print(f"  {id_to_name_expected[r.source]} --[{r.kind.value}]--> {id_to_name_expected[r.target]}"
              + (f"  (mult {r.source_mult or '-'}/{r.target_mult or '-'})" if r.source_mult or r.target_mult else ""))

    print("\n--- actual (model) relationships, with evidence ---")
    for r in actual.relationships:
        src = id_to_name_actual.get(r.source, f"<unknown:{r.source}>")
        tgt = id_to_name_actual.get(r.target, f"<unknown:{r.target}>")
        print(f"  {src} --[{r.kind.value}]--> {tgt}  conf={r.confidence}")
        print(f"    evidence: {r.evidence!r}")

    d = diff(expected, actual)
    print("\n--- structural diff (relationships) ---")
    print(f"  added (hallucinated):   {d.added_relationships}")
    print(f"  removed (missed):       {d.removed_relationships}")
    print(f"  changed (wrong kind):   {[(c.source, c.target, c.expected_kind.value, c.actual_kind.value) for c in d.changed_relationships]}")
    print()
