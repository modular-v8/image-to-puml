"""T2.13 verification: regenerate() end to end. Not part of the shipped
package."""

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

from umlregen.api import regenerate
from umlregen.config import Config
from umlregen.render.plantuml import render

config = Config()
print("model:", config.model_id)

image_bytes = Path("corpus/img/ecommerce_checkout.png").read_bytes()
result = regenerate(image_bytes, config)

print(f"classes: {len(result.diagram.classes)}, relationships: {len(result.diagram.relationships)}")
print(f"cost: ${result.cost_usd}, latency: {result.latency_seconds:.2f}s")
print(f"warnings: {result.warnings}")
print(f".puml length: {len(result.puml)} chars")

out_path = Path("runs/smoke_api_output.svg")
render(result.puml, "svg", out_path)
print(f"rendered OK -> {out_path}")
