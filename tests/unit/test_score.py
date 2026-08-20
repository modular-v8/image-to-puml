"""T2.18/T2.20: eval/score.py against hand-computed fixtures -- every
metric must match the hand calculation exactly, not just "look
reasonable". Offline.

Scenario (worked by hand in comments below):
  expected: classes A(attr1,attr2), B(m1), C()
  actual:   classes A(attr1,attr3), B(m1), D()   -- C missing, D hallucinated
  expected relationships: A->B association, B->C inheritance, A->C dependency
  actual relationships:   A->B composition (wrong kind), A->D dependency (hallucinated)
"""

import pytest

from umlregen.eval.score import score
from umlregen.ir.diff import diff
from umlregen.ir.models import Class, Diagram, Member, RelKind, Relationship


def _expected() -> Diagram:
    return Diagram(
        classes=[
            Class(id="A", name="A", kind="class", attributes=[Member(name="attr1"), Member(name="attr2")]),
            Class(id="B", name="B", kind="class", attributes=[Member(name="m1")]),
            Class(id="C", name="C", kind="class"),
        ],
        relationships=[
            Relationship(source="A", target="B", kind=RelKind.ASSOCIATION, confidence=0.9),
            Relationship(source="B", target="C", kind=RelKind.INHERITANCE, confidence=0.9),
            Relationship(source="A", target="C", kind=RelKind.DEPENDENCY, confidence=0.9),
        ],
    )


def _actual() -> Diagram:
    return Diagram(
        classes=[
            Class(id="A", name="A", kind="class", attributes=[Member(name="attr1"), Member(name="attr3")]),
            Class(id="B", name="B", kind="class", attributes=[Member(name="m1")]),
            Class(id="D", name="D", kind="class"),
        ],
        relationships=[
            Relationship(source="A", target="B", kind=RelKind.COMPOSITION, confidence=0.9),
            Relationship(source="A", target="D", kind=RelKind.DEPENDENCY, confidence=0.9),
        ],
    )


def test_identity_case_yields_perfect_scores() -> None:
    expected = _expected()

    result = score(expected, expected.model_copy(deep=True))

    assert result.class_recall == 1.0
    assert result.class_precision == 1.0
    assert result.class_f1 == 1.0
    assert result.member_f1 == 1.0
    assert result.relationship_f1 == 1.0
    assert result.pair_recall == 1.0
    assert result.kind_accuracy_given_correct_pair == 1.0


def test_hand_computed_scenario_matches_by_hand_calculation() -> None:
    result = score(_expected(), _actual())

    # classes: matched={A,B} (2), expected=3, actual=3
    assert result.class_recall == pytest.approx(2 / 3)
    assert result.class_precision == pytest.approx(2 / 3)
    assert result.class_f1 == pytest.approx(2 / 3)

    # members (matched classes A, B only):
    #   A: expected {attr1,attr2}, actual {attr1,attr3} -> tp=1, fp=1, fn=1
    #   B: expected {m1}, actual {m1} -> tp=1, fp=0, fn=0
    #   totals: tp=2, fp=1, fn=1 -> precision=recall=2/3
    assert result.member_f1 == pytest.approx(2 / 3)

    # relationships: expected=3 (A-B assoc, B-C inherit, A-C dep)
    #                actual=2 (A-B composition [wrong kind], A-D dep [hallucinated])
    #   removed pairs: (B,C), (A,C) -> 2
    #   added pairs: (A,D) -> 1
    #   changed pairs: (A,B) assoc->composition -> 1
    #   rel_fn = 2+1=3, rel_fp=1+1=2, rel_tp = 3-3=0
    assert result.relationship_f1 == pytest.approx(0.0)

    # pair_recall: matched_pairs = 3 - 2(removed) = 1; 1/3
    assert result.pair_recall == pytest.approx(1 / 3)

    # kind accuracy given correct pair: matched_pairs=1, changed=1 -> 0/1
    assert result.kind_accuracy_given_correct_pair == pytest.approx(0.0)


def test_diff_is_empty_for_identity_case() -> None:
    expected = _expected()
    assert diff(expected, expected.model_copy(deep=True)).is_empty


def test_diff_missing_relationship_case() -> None:
    expected = _expected()
    actual = expected.model_copy(deep=True)
    actual.relationships = actual.relationships[:-1]  # drop A->C dependency

    result = diff(expected, actual)

    assert len(result.removed_relationships) == 1
    assert result.removed_relationships[0] == ("a", "c", "dependency")
    assert result.added_relationships == []
    assert result.changed_relationships == []


def test_diff_wrong_kind_case() -> None:
    expected = _expected()
    actual = expected.model_copy(deep=True)
    actual.relationships[0].kind = RelKind.COMPOSITION  # A->B was association

    result = diff(expected, actual)

    assert len(result.changed_relationships) == 1
    assert result.changed_relationships[0].expected_kind == RelKind.ASSOCIATION
    assert result.changed_relationships[0].actual_kind == RelKind.COMPOSITION
    assert result.added_relationships == []
    assert result.removed_relationships == []


def test_diff_hallucinated_relationship_case() -> None:
    expected = _expected()
    actual = expected.model_copy(deep=True)
    actual.relationships.append(
        Relationship(source="C", target="A", kind=RelKind.DEPENDENCY, confidence=0.9)
    )

    result = diff(expected, actual)

    assert result.added_relationships == [("c", "a", "dependency")]
    assert result.removed_relationships == []
    assert result.changed_relationships == []
