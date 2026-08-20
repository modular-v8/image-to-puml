"""`review.md` sidecar (T4.7): lists every relationship whose confidence
falls below the configured threshold, alongside its `.puml` line number
and the model's recorded evidence -- so a human's editing time
concentrates on the elements the pipeline itself is least sure about,
instead of a blind read of the whole diagram.

Line numbers come from `generate/puml.py`'s `ir_to_puml_with_line_map`,
the same function that produces the `.puml` this sidecar is meant to
accompany -- never re-derived independently, so the two can't drift.
"""

from __future__ import annotations

from pathlib import Path

from umlregen.generate.puml import derive_aliases, ir_to_puml_with_line_map
from umlregen.ir.models import Diagram, Relationship


def _describe(rel: Relationship, aliases: dict[str, str]) -> str:
    return f"{aliases[rel.source]} {rel.kind.value} {aliases[rel.target]}"


def build_review(diagram: Diagram, threshold: float) -> str:
    """Returns `review.md`'s content as a string. A diagram with nothing
    below threshold still produces a valid, small file saying so -- that
    is a legitimate good outcome (nothing needs review), not an error.
    """
    _, line_map = ir_to_puml_with_line_map(diagram)
    aliases = derive_aliases(diagram.classes)

    flagged = [rel for rel in diagram.relationships if rel.confidence < threshold]
    flagged.sort(key=lambda rel: line_map[id(rel)])

    lines = ["# Review", "", f"Confidence threshold: {threshold:.2f}", ""]
    if not flagged:
        lines.append("No relationships fall below the confidence threshold.")
        return "\n".join(lines) + "\n"

    lines.append(f"{len(flagged)} relationship(s) below threshold:")
    lines.append("")
    for rel in flagged:
        line_no = line_map[id(rel)]
        lines.append(f"- **`.puml:{line_no}`** `{_describe(rel, aliases)}` -- confidence {rel.confidence:.2f}")
        lines.append(f"  - evidence: {rel.evidence or '(none recorded)'}")
    return "\n".join(lines) + "\n"


def write_review(diagram: Diagram, threshold: float, out_path: str | Path) -> Path:
    """Writes `build_review`'s content to `out_path`, creating parent
    directories as needed, and returns the path written."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_review(diagram, threshold), encoding="utf-8")
    return out_path
