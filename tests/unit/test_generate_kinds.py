"""Golden-file tests, one per RelKind: the exact emitted line for a known
two-class IR. These are the tests that catch a reversed arrow -- the single
most likely silent bug in this project."""

import pytest

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Class, Diagram, RelKind, Relationship

EXPECTED_LINES = {
    RelKind.INHERITANCE: "Alpha --|> Beta",
    RelKind.REALIZATION: "Alpha ..|> Beta",
    RelKind.COMPOSITION: "Alpha *-- Beta",
    RelKind.AGGREGATION: "Alpha o-- Beta",
    RelKind.ASSOCIATION: "Alpha -- Beta",
    RelKind.DIRECTED_ASSOCIATION: "Alpha --> Beta",
    RelKind.DEPENDENCY: "Alpha ..> Beta",
}


def _two_class_diagram(kind: RelKind) -> Diagram:
    return Diagram(
        classes=[
            Class(id="Alpha", name="Alpha", kind="class"),
            Class(id="Beta", name="Beta", kind="class"),
        ],
        relationships=[
            Relationship(source="Alpha", target="Beta", kind=kind, confidence=0.9)
        ],
    )


@pytest.mark.parametrize("kind", list(RelKind))
def test_golden_relationship_line(kind: RelKind) -> None:
    puml = ir_to_puml(_two_class_diagram(kind))
    assert EXPECTED_LINES[kind] in puml.splitlines()
