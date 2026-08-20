"""T4.16: calibrate review.md's confidence threshold. For each candidate
threshold, reports how many relationships in the shipped configuration's
extracted output get flagged and what fraction of those are actually
wrong (hallucinated pair, or right pair wrong kind) -- against ground
truth, using the corpus+holdout cache already populated by T3.42/T4.22.
Should cost $0 if the cache is warm; prints a cost total either way so
a stale-cache surprise is visible rather than silent."""

import os
import sys
from collections import Counter
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
from umlregen.ir.diff import diff, normalize_name
from umlregen.ir.models import Diagram
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


raw_client = OpenRouterClient(model_id=DEFAULT_EVAL_MODEL_ID, timeout=90.0, requests_per_minute=40.0)
client = CachedVisionClient(raw_client, model_id=DEFAULT_EVAL_MODEL_ID, cache_dir=Path(".cache"))

records: list[tuple[float, bool, str]] = []  # (confidence, is_wrong, diagram_name)
total_cost = 0.0

for ir_dir, img_dir in [
    (Path("corpus/ir"), Path("corpus/img")),
    (Path("corpus/holdout/ir"), Path("corpus/holdout/img")),
]:
    for ir_path in sorted(ir_dir.glob("*.json")):
        name = ir_path.stem
        img_path = _find_image(img_dir, name)
        if img_path is None:
            continue
        expected = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        image_bytes = img_path.read_bytes()

        try:
            stage_a, cost_a = extract_classes(client, image_bytes)
            actual, cost_b = extract_relationships(client, image_bytes, stage_a)
        except Exception as exc:
            print(f"SKIP {name}: {type(exc).__name__}: {exc}")
            continue
        total_cost += cost_a + cost_b

        d = diff(expected, actual)
        wrong_pairs = {(s, t) for s, t, _ in d.added_relationships}
        wrong_pairs |= {(rc.source, rc.target) for rc in d.changed_relationships}

        id_to_name = {c.id: normalize_name(c.name) for c in actual.classes}
        for rel in actual.relationships:
            source = id_to_name.get(rel.source, rel.source)
            target = id_to_name.get(rel.target, rel.target)
            is_wrong = (source, target) in wrong_pairs
            records.append((rel.confidence, is_wrong, name))

print(f"\nTotal cost for this analysis: ${total_cost:.4f}")
print(f"Total relationships analyzed: {len(records)}")

conf_counts = Counter(round(r[0], 3) for r in records)
print("Confidence value distribution:", dict(sorted(conf_counts.items())))

total_wrong = sum(1 for r in records if r[1])
print(f"Total actually-wrong relationships: {total_wrong}/{len(records)}\n")

print(f"{'threshold':>9}  {'flagged':>7}  {'precision':>9}  {'recall_of_errors':>17}")
for threshold in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]:
    flagged = [r for r in records if r[0] < threshold]
    flagged_wrong = sum(1 for r in flagged if r[1])
    precision = flagged_wrong / len(flagged) if flagged else None
    recall = flagged_wrong / total_wrong if total_wrong else None
    p_str = f"{precision:.0%}" if precision is not None else "n/a"
    r_str = f"{recall:.0%}" if recall is not None else "n/a"
    print(f"{threshold:>9.1f}  {len(flagged):>7d}  {p_str:>9}  {r_str:>17}")
