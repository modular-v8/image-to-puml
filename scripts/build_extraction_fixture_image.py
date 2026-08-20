"""Renders a stable, dedicated test image for T2.14's extraction fixtures,
decoupled from corpus/img/ (which T2.16's build_corpus() legitimately
overwrites with restyled renders). Not part of the shipped package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Diagram
from umlregen.render.plantuml import render

ir_path = Path("corpus/ir/ecommerce_checkout.json")
diagram = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
puml_text = ir_to_puml(diagram)

out_path = Path("tests/fixtures/ecommerce_checkout.png")
render(puml_text, "png", out_path)
print(f"wrote {out_path}")
