"""Shuffling a multi-class IR's lists must never change the generated
output -- required for the spec's byte-identical-repeat-run guarantee."""

import random

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Class, Diagram, Member, RelKind, Relationship

SHUFFLE_ROUNDS = 10


def _sample_diagram() -> Diagram:
    return Diagram(
        classes=[
            Class(
                id="Animal",
                name="Animal",
                kind="class",
                attributes=[Member(visibility="+", name="name", type="str")],
            ),
            Class(id="Dog", name="Dog", kind="class"),
            Class(id="Shape", name="Shape", kind="interface"),
            Class(id="Circle", name="Circle", kind="class"),
            Class(id="Engine", name="Engine", kind="class"),
            Class(id="Car", name="Car", kind="class"),
        ],
        relationships=[
            Relationship(source="Dog", target="Animal", kind=RelKind.INHERITANCE, confidence=0.9),
            Relationship(source="Circle", target="Shape", kind=RelKind.REALIZATION, confidence=0.9),
            Relationship(
                source="Car",
                target="Engine",
                kind=RelKind.COMPOSITION,
                confidence=0.9,
                source_mult="1",
                target_mult="1",
            ),
        ],
    )


def test_shuffled_ir_produces_byte_identical_output() -> None:
    diagram = _sample_diagram()
    baseline = ir_to_puml(diagram)

    rng = random.Random(1234)
    for _ in range(SHUFFLE_ROUNDS):
        shuffled_classes = diagram.classes[:]
        shuffled_relationships = diagram.relationships[:]
        rng.shuffle(shuffled_classes)
        rng.shuffle(shuffled_relationships)

        shuffled = diagram.model_copy(
            update={"classes": shuffled_classes, "relationships": shuffled_relationships}
        )

        assert ir_to_puml(shuffled) == baseline
