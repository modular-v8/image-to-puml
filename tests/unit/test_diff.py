"""T2.17's own acceptance criteria for ir/diff.py: an IR diffed against
itself is empty, and a single-relationship-kind change yields exactly one
changed entry naming both kinds. The fuller known-answer fixture suite
(identity, missing-relationship, wrong-kind, hallucinated-relationship)
is T2.20's job, in test_score.py. Offline."""

from umlregen.ir.diff import diff
from umlregen.ir.models import Class, Diagram, RelKind, Relationship


def _sample_diagram() -> Diagram:
    return Diagram(
        classes=[
            Class(id="A", name="Alpha", kind="class"),
            Class(id="B", name="Beta", kind="class"),
        ],
        relationships=[
            Relationship(source="A", target="B", kind=RelKind.ASSOCIATION, confidence=0.9),
        ],
    )


def test_diagram_diffed_against_itself_is_empty() -> None:
    diagram = _sample_diagram()

    result = diff(diagram, diagram)

    assert result.is_empty


def test_single_relationship_kind_change_yields_one_changed_entry_naming_both_kinds() -> None:
    expected = _sample_diagram()
    actual = expected.model_copy(deep=True)
    actual.relationships[0].kind = RelKind.DEPENDENCY

    result = diff(expected, actual)

    assert result.added_relationships == []
    assert result.removed_relationships == []
    assert len(result.changed_relationships) == 1
    change = result.changed_relationships[0]
    assert change.expected_kind == RelKind.ASSOCIATION
    assert change.actual_kind == RelKind.DEPENDENCY
