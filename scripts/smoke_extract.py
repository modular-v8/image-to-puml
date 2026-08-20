"""T2.10/T2.11 live verification: run stage A + stage B extraction against
the T1.22 gate diagram using the real provider. Not part of the shipped
package."""

import json
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

from umlregen.config import DEFAULT_MODEL_ID
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.openrouter import OpenRouterClient

print("model:", DEFAULT_MODEL_ID)

raw_client = OpenRouterClient(model_id=DEFAULT_MODEL_ID, timeout=90.0)
client = CachedVisionClient(raw_client, model_id=DEFAULT_MODEL_ID, cache_dir=Path(".cache"))
image_bytes = Path("tests/fixtures/ecommerce_checkout.png").read_bytes()

print("=" * 70)
print("STAGE A")
stage_a, cost_a = extract_classes(client, image_bytes)
print(f"classes ({len(stage_a.classes)}), cost=${cost_a}:")
for cls in stage_a.classes:
    print(f"  - id={cls.id!r} name={cls.name!r} kind={cls.kind} stereotype={cls.stereotype!r}")
    for attr in cls.attributes:
        print(f"      attr: {attr.visibility or ''}{attr.name}: {attr.type} static={attr.is_static}")
    for method in cls.methods:
        print(f"      method: {method.visibility or ''}{method.name}({method.params}): {method.type} abstract={method.is_abstract}")
print("warnings:", stage_a.warnings)

print("=" * 70)
print("STAGE B")
full, cost_b = extract_relationships(client, image_bytes, stage_a)
print(f"relationships ({len(full.relationships)}), cost=${cost_b}:")
for rel in full.relationships:
    print(f"  - {rel.source} -{rel.kind.value}-> {rel.target} (mult {rel.source_mult}/{rel.target_mult}) evidence={rel.evidence!r}")
print("warnings:", full.warnings)
