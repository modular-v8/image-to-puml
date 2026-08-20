"""Corpus construction: for each hand-authored IR in corpus/ir/, generate
`.puml` and render a PNG. Rendered images intentionally vary in visual
style across the set -- see spec's prior decisions -- so the corpus
doesn't teach a vision model a single fixed presentation.

`ir_to_puml` itself stays untouched and single-purpose (pure IR -> the
canonical `.puml` a user actually gets); style variation is layered on
top here, specifically for corpus renders, not for generation in general.
"""

from __future__ import annotations

from pathlib import Path

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Diagram
from umlregen.render.plantuml import render

_IR_DIR = Path("corpus/ir")
_PUML_DIR = Path("corpus/puml")
_IMG_DIR = Path("corpus/img")

# Skinparam blocks, not named `!theme` files -- these are long-standing
# core PlantUML options guaranteed to exist across versions, unlike a
# named theme which depends on a bundled theme file that can vary or be
# renamed between releases. `handwritten true` was tried and dropped: it
# depends on a handwritten-style font that isn't guaranteed to be
# installed, and without one it silently renders identically to plain --
# no visual distinctiveness, the entire point of varying style here.
_STYLES: list[str] = [
    "",  # plain: whatever ir_to_puml already emits, no extra styling
    (
        "skinparam backgroundColor #1e1e1e\n"
        "skinparam classBackgroundColor #2d2d2d\n"
        "skinparam classFontColor #ffffff\n"
        "skinparam classBorderColor #569cd6\n"
        "skinparam arrowColor #569cd6\n"
    ),
    (
        "skinparam roundCorner 25\n"
        "skinparam shadowing false\n"
        "skinparam classBackgroundColor #fff4e0\n"
        "skinparam classBorderColor #d4832a\n"
        "skinparam arrowColor #d4832a\n"
    ),
    "skinparam monochrome true\n",
]


def _apply_style(puml_text: str, style: str) -> str:
    if not style:
        return puml_text
    return puml_text.replace("@startuml\n", f"@startuml\n{style}", 1)


def build_corpus(
    ir_dir: Path = _IR_DIR, puml_dir: Path = _PUML_DIR, img_dir: Path = _IMG_DIR
) -> list[Path]:
    """Regenerates every corpus fixture from its IR: a styled `.puml` and
    a rendered PNG. Reproducible -- style assignment is deterministic
    (sorted filename order, cycled through `_STYLES`), never random.
    """
    puml_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for index, ir_path in enumerate(sorted(ir_dir.glob("*.json"))):
        diagram = Diagram.model_validate_json(ir_path.read_text(encoding="utf-8"))
        styled_puml = _apply_style(ir_to_puml(diagram), _STYLES[index % len(_STYLES)])

        (puml_dir / f"{ir_path.stem}.puml").write_text(styled_puml, encoding="utf-8")

        img_path = img_dir / f"{ir_path.stem}.png"
        render(styled_puml, "png", img_path)
        written.append(img_path)

    return written


if __name__ == "__main__":
    for path in build_corpus():
        print(f"wrote {path}")
