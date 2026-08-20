"""The typed IR: the single hand-off between perception and generation.

Nothing downstream of `Diagram` talks to a vision model, and nothing upstream
of it talks to PlantUML -- this module is the seam.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RelKind(str, Enum):
    """The seven relationship kinds this tool distinguishes."""

    INHERITANCE = "inheritance"
    REALIZATION = "realization"
    COMPOSITION = "composition"
    AGGREGATION = "aggregation"
    ASSOCIATION = "association"
    DIRECTED_ASSOCIATION = "directed_association"
    DEPENDENCY = "dependency"


class BBox(BaseModel):
    """A class's bounding box in source-image pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=0)
    h: int = Field(ge=0)


class Member(BaseModel):
    """An attribute or a method on a class."""

    visibility: Literal["+", "-", "#", "~"] | None = None
    name: str
    type: str | None = None
    params: str | None = None  # methods only
    is_static: bool = False
    is_abstract: bool = False


class Class(BaseModel):
    """A class, interface, abstract class, or enum extracted from the diagram."""

    id: str  # stable alias, derived from the name, unique within the diagram
    name: str
    kind: Literal["class", "interface", "abstract", "enum"]
    stereotype: str | None = None
    attributes: list[Member] = Field(default_factory=list)
    methods: list[Member] = Field(default_factory=list)
    bbox: BBox | None = None


class Relationship(BaseModel):
    """A typed, directed edge between two classes.

    Direction convention: `source` is the class named first when the
    relationship is read aloud as an English sentence. The generator owns
    one template per `RelKind` and places the arrowhead or diamond on the
    correct end from that convention -- this docstring is the single place
    the convention is defined; everywhere else references it rather than
    restating it.

    One worked example per kind (source -> target):
        inheritance:           Dog is-a Animal            -> source=Dog, target=Animal
        realization:           Circle implements Shape    -> source=Circle, target=Shape
        composition:           Car has-a Engine           -> source=Car, target=Engine
        aggregation:           Library has Book           -> source=Library, target=Book
        association:           Student takes Course       -> source=Student, target=Course
        directed_association:  Customer places Order      -> source=Customer, target=Order
        dependency:             Order depends-on Gateway    -> source=Order, target=Gateway
    """

    source: str  # Class.id
    target: str  # Class.id
    kind: RelKind
    source_mult: str | None = None
    target_mult: str | None = None
    label: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str | None = None


class Note(BaseModel):
    """A free-text note, optionally attached to a class."""

    text: str
    class_id: str | None = None  # None means a floating, unattached note


class Diagram(BaseModel):
    """The root IR: everything extracted from one input image."""

    name: str | None = None
    classes: list[Class] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_invariants(self) -> Diagram:
        """Enforces the two structural invariants the rest of the pipeline
        relies on: unique class ids, and relationships that only ever point
        at classes that exist. Raising here (rather than silently repairing)
        is deliberate -- callers that need to repair untrusted extraction
        output should go through `normalize()` instead, which filters bad
        relationships before construction rather than after.
        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for cls in self.classes:
            if cls.id in seen:
                duplicates.add(cls.id)
            seen.add(cls.id)
        if duplicates:
            raise ValueError(f"duplicate Class.id values: {sorted(duplicates)}")

        known_ids = seen
        for rel in self.relationships:
            if rel.source not in known_ids:
                raise ValueError(
                    f"relationship source {rel.source!r} does not reference "
                    "a known Class.id"
                )
            if rel.target not in known_ids:
                raise ValueError(
                    f"relationship target {rel.target!r} does not reference "
                    "a known Class.id"
                )
        return self

    @classmethod
    def normalize(cls, data: dict[str, Any]) -> Diagram:
        """Repairs raw (untrusted) extraction data into a valid `Diagram`.

        Unlike `model_validate`, this never rejects a diagram outright for a
        dangling relationship: any relationship whose source or target isn't
        among the given classes is dropped, and a human-readable entry is
        appended to `warnings` naming what was dropped and why. Duplicate
        class ids are not repaired here -- there's no safe automatic fix --
        so they still raise via the invariant check above.
        """
        classes_data = data.get("classes", [])
        known_ids = {c["id"] for c in classes_data}

        warnings = list(data.get("warnings", []))
        kept_relationships = []
        for rel in data.get("relationships", []):
            source, target = rel.get("source"), rel.get("target")
            if source in known_ids and target in known_ids:
                kept_relationships.append(rel)
                continue
            warnings.append(
                f"dropped {rel.get('kind')} relationship "
                f"{source!r} -> {target!r}: references a class not in the diagram"
            )

        cleaned = {**data, "relationships": kept_relationships, "warnings": warnings}
        return cls.model_validate(cleaned)
