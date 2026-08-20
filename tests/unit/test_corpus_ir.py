"""T2.15's acceptance criterion as a regression guard: at least 8 valid IR
files in corpus/ir/, collectively exercising all seven RelKind values,
each individually passing IR validation. Offline -- no network."""

from pathlib import Path

from umlregen.ir.models import Diagram, RelKind

_CORPUS_IR_DIR = Path(__file__).resolve().parent.parent.parent / "corpus" / "ir"


def test_corpus_has_at_least_eight_valid_ir_files() -> None:
    ir_files = sorted(_CORPUS_IR_DIR.glob("*.json"))
    assert len(ir_files) >= 8, f"expected >= 8 corpus IR files, found {len(ir_files)}"

    for path in ir_files:
        Diagram.model_validate_json(path.read_text(encoding="utf-8"))  # raises if invalid


def test_corpus_collectively_covers_all_seven_relationship_kinds() -> None:
    seen_kinds: set[RelKind] = set()
    for path in _CORPUS_IR_DIR.glob("*.json"):
        diagram = Diagram.model_validate_json(path.read_text(encoding="utf-8"))
        seen_kinds.update(rel.kind for rel in diagram.relationships)

    assert seen_kinds == set(RelKind)
