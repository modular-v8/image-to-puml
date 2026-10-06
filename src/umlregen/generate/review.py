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

from pydantic import BaseModel

from umlregen.generate.puml import derive_aliases, ir_to_puml_with_line_map
from umlregen.ir.models import Diagram

_NO_EVIDENCE = "(none recorded)"


class ReviewItem(BaseModel):
    """One flagged relationship, as `review.md` and the web UI both show it."""

    line: int
    source: str
    kind: str
    target: str
    confidence: float
    evidence: str | None


def flagged_items(diagram: Diagram, threshold: float) -> list[ReviewItem]:
    """Relationships below `threshold`, in `.puml` line order. The one
    selection `build_review` and the UI share, so they can't disagree."""
    _, line_map = ir_to_puml_with_line_map(diagram)
    aliases = derive_aliases(diagram.classes)

    flagged = [rel for rel in diagram.relationships if rel.confidence < threshold]
    flagged.sort(key=lambda rel: line_map[id(rel)])

    return [
        ReviewItem(
            line=line_map[id(rel)],
            source=aliases[rel.source],
            kind=rel.kind.value,
            target=aliases[rel.target],
            confidence=rel.confidence,
            evidence=rel.evidence,
        )
        for rel in flagged
    ]


def build_review(diagram: Diagram, threshold: float) -> str:
    """Returns `review.md`'s content as a string. A diagram with nothing
    below threshold still produces a valid, small file saying so -- that
    is a legitimate good outcome (nothing needs review), not an error.
    """
    flagged = flagged_items(diagram, threshold)

    lines = ["# Review", "", f"Confidence threshold: {threshold:.2f}", ""]
    if not flagged:
        lines.append("No relationships fall below the confidence threshold.")
        return "\n".join(lines) + "\n"

    lines.append(f"{len(flagged)} relationship(s) below threshold:")
    lines.append("")
    for item in flagged:
        lines.append(
            f"- **`.puml:{item.line}`** `{item.source} {item.kind} {item.target}` -- confidence {item.confidence:.2f}"
        )
        lines.append(f"  - evidence: {item.evidence or _NO_EVIDENCE}")
    return "\n".join(lines) + "\n"


def write_review(diagram: Diagram, threshold: float, out_path: str | Path) -> Path:
    """Writes `build_review`'s content to `out_path`, creating parent
    directories as needed, and returns the path written."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_review(diagram, threshold), encoding="utf-8")
    return out_path
