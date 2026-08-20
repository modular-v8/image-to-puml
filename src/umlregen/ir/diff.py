"""Structural diff between two IRs: what's added, removed, or changed --
classes, members, relationships. Shared by the verification loop (a
render's re-extracted IR against the one that generated it) and the
evaluation scorer (a prediction against ground truth) -- see plan.md's
Architecture. Depends on nothing else in the package.

Relationships reference `Class.id`, which is assigned independently per
diagram (extraction-run-specific, or hand-authored) and is never stable
across two diagrams being compared -- so relationship identity here is
resolved through the *class names* at each end, not the raw ids.

Relationship identity is the `(source, target)` pair (after name
normalization); `kind` is compared as an attribute of that pair, not part
of its identity. That's what lets a kind-only change surface as one
`changed` entry naming both kinds, rather than as an unrelated
add-of-the-new-kind plus remove-of-the-old-kind at the same two classes --
which is what T2.18's "pair recall" and "kind accuracy given a correct
pair" metrics need to be able to tell apart.
"""

from __future__ import annotations

from pydantic import BaseModel

from umlregen.ir.models import Class, Diagram, Member, RelKind


def normalize_name(name: str) -> str:
    """casefold + strip + collapse internal whitespace -- the one name-
    matching rule used everywhere two IRs are compared."""
    return " ".join(name.strip().casefold().split())


class MemberDiff(BaseModel):
    added: list[str] = []
    removed: list[str] = []


class ClassChange(BaseModel):
    name: str
    expected_kind: str | None = None
    actual_kind: str | None = None
    attributes: MemberDiff = MemberDiff()
    methods: MemberDiff = MemberDiff()

    @property
    def kind_changed(self) -> bool:
        return self.expected_kind != self.actual_kind


class RelationshipChange(BaseModel):
    source: str
    target: str
    expected_kind: RelKind
    actual_kind: RelKind


class DiagramDiff(BaseModel):
    added_classes: list[str] = []
    removed_classes: list[str] = []
    changed_classes: list[ClassChange] = []

    added_relationships: list[tuple[str, str, str]] = []
    removed_relationships: list[tuple[str, str, str]] = []
    changed_relationships: list[RelationshipChange] = []

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_classes
            or self.removed_classes
            or self.changed_classes
            or self.added_relationships
            or self.removed_relationships
            or self.changed_relationships
        )


def _member_names(members: list[Member]) -> set[str]:
    return {normalize_name(m.name) for m in members}


def _diff_members(expected: list[Member], actual: list[Member]) -> MemberDiff:
    expected_names = _member_names(expected)
    actual_names = _member_names(actual)
    return MemberDiff(
        added=sorted(actual_names - expected_names),
        removed=sorted(expected_names - actual_names),
    )


def _diff_classes(
    expected: Diagram, actual: Diagram
) -> tuple[list[str], list[str], list[ClassChange]]:
    expected_by_name: dict[str, Class] = {normalize_name(c.name): c for c in expected.classes}
    actual_by_name: dict[str, Class] = {normalize_name(c.name): c for c in actual.classes}

    added = sorted(set(actual_by_name) - set(expected_by_name))
    removed = sorted(set(expected_by_name) - set(actual_by_name))

    changed: list[ClassChange] = []
    for key in sorted(set(expected_by_name) & set(actual_by_name)):
        exp_cls, act_cls = expected_by_name[key], actual_by_name[key]
        attr_diff = _diff_members(exp_cls.attributes, act_cls.attributes)
        method_diff = _diff_members(exp_cls.methods, act_cls.methods)
        kind_differs = exp_cls.kind != act_cls.kind
        if kind_differs or attr_diff.added or attr_diff.removed or method_diff.added or method_diff.removed:
            changed.append(
                ClassChange(
                    name=exp_cls.name,
                    expected_kind=exp_cls.kind,
                    actual_kind=act_cls.kind,
                    attributes=attr_diff,
                    methods=method_diff,
                )
            )

    return added, removed, changed


def _class_id_to_normalized_name(diagram: Diagram) -> dict[str, str]:
    return {c.id: normalize_name(c.name) for c in diagram.classes}


def _relationship_pair_kind(diagram: Diagram) -> dict[tuple[str, str], RelKind]:
    """Maps (normalized_source_name, normalized_target_name) -> kind.

    If a diagram reports more than one relationship kind for the same
    pair of classes (unusual for a UML class diagram), the first one
    encountered wins -- a deliberate simplification, not a guarantee of
    completeness for that pathological case.
    """
    id_to_name = _class_id_to_normalized_name(diagram)
    pairs: dict[tuple[str, str], RelKind] = {}
    for rel in diagram.relationships:
        source_name = id_to_name.get(rel.source, rel.source)
        target_name = id_to_name.get(rel.target, rel.target)
        pairs.setdefault((source_name, target_name), rel.kind)
    return pairs


def _diff_relationships(
    expected: Diagram, actual: Diagram
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], list[RelationshipChange]]:
    expected_pairs = _relationship_pair_kind(expected)
    actual_pairs = _relationship_pair_kind(actual)

    added: list[tuple[str, str, str]] = []
    removed: list[tuple[str, str, str]] = []
    changed: list[RelationshipChange] = []

    for pair in sorted(set(expected_pairs) | set(actual_pairs)):
        source, target = pair
        expected_kind = expected_pairs.get(pair)
        actual_kind = actual_pairs.get(pair)

        if expected_kind is not None and actual_kind is not None:
            if expected_kind != actual_kind:
                changed.append(
                    RelationshipChange(
                        source=source, target=target,
                        expected_kind=expected_kind, actual_kind=actual_kind,
                    )
                )
        elif expected_kind is not None:
            removed.append((source, target, expected_kind.value))
        else:
            assert actual_kind is not None
            added.append((source, target, actual_kind.value))

    return added, removed, changed


def diff(expected: Diagram, actual: Diagram) -> DiagramDiff:
    """Structural diff from `expected`'s perspective: `added` is present
    only in `actual`, `removed` is present only in `expected`, `changed`
    is present in both but differs.
    """
    added_classes, removed_classes, changed_classes = _diff_classes(expected, actual)
    added_rels, removed_rels, changed_rels = _diff_relationships(expected, actual)
    return DiagramDiff(
        added_classes=added_classes,
        removed_classes=removed_classes,
        changed_classes=changed_classes,
        added_relationships=added_rels,
        removed_relationships=removed_rels,
        changed_relationships=changed_rels,
    )
