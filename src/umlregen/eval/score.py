"""Scoring on top of `ir/diff.py`'s structural diff: the five metrics
spec requires an evaluation run to report -- class recall/precision/F1,
member F1 within matched classes, relationship F1 on the full triple,
pair recall (ignoring kind), and kind accuracy given a correct pair.
"""

from __future__ import annotations

from pydantic import BaseModel

from umlregen.ir.diff import diff, normalize_name
from umlregen.ir.models import Diagram


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


class ScoreResult(BaseModel):
    class_recall: float
    class_precision: float
    class_f1: float
    member_f1: float
    relationship_f1: float
    pair_recall: float
    kind_accuracy_given_correct_pair: float


def _member_metrics(expected: Diagram, actual: Diagram) -> tuple[int, int, int]:
    """Member-level (TP, FP, FN), pooled across every matched class (a
    class present, by normalized name, in both diagrams). Members of an
    unmatched class don't count here -- that's already captured by class
    recall/precision.
    """
    expected_by_name = {normalize_name(c.name): c for c in expected.classes}
    actual_by_name = {normalize_name(c.name): c for c in actual.classes}
    matched = set(expected_by_name) & set(actual_by_name)

    tp = fp = fn = 0
    for key in matched:
        exp_cls, act_cls = expected_by_name[key], actual_by_name[key]
        exp_members = {normalize_name(m.name) for m in exp_cls.attributes + exp_cls.methods}
        act_members = {normalize_name(m.name) for m in act_cls.attributes + act_cls.methods}
        tp += len(exp_members & act_members)
        fp += len(act_members - exp_members)
        fn += len(exp_members - act_members)

    return tp, fp, fn


def score(expected: Diagram, actual: Diagram) -> ScoreResult:
    """Scores `actual` against `expected` (ground truth)."""
    d = diff(expected, actual)

    # --- classes ---
    total_expected_classes = len(expected.classes)
    total_actual_classes = len(actual.classes)
    matched_classes = total_expected_classes - len(d.removed_classes)
    class_recall = _safe_div(matched_classes, total_expected_classes)
    class_precision = _safe_div(matched_classes, total_actual_classes)
    class_f1 = _f1(class_precision, class_recall)

    # --- members, within matched classes only ---
    member_tp, member_fp, member_fn = _member_metrics(expected, actual)
    member_precision = _safe_div(member_tp, member_tp + member_fp)
    member_recall = _safe_div(member_tp, member_tp + member_fn)
    member_f1 = _f1(member_precision, member_recall)

    # --- relationships, on the full (source, target, kind) triple ---
    # Under diff.py's documented simplification (at most one kind per
    # (source, target) pair), a relationship *count* and a *pair* count
    # coincide, which is what lets these be derived directly from the
    # diff's added/removed/changed counts rather than re-deriving pairs.
    total_expected_rels = len(expected.relationships)
    total_actual_rels = len(actual.relationships)
    rel_fn = len(d.removed_relationships) + len(d.changed_relationships)
    rel_fp = len(d.added_relationships) + len(d.changed_relationships)
    rel_tp = total_expected_rels - rel_fn
    rel_precision = _safe_div(rel_tp, total_actual_rels)
    rel_recall = _safe_div(rel_tp, total_expected_rels)
    relationship_f1 = _f1(rel_precision, rel_recall)

    # --- pair recall, ignoring kind ---
    matched_pairs = total_expected_rels - len(d.removed_relationships)
    pair_recall = _safe_div(matched_pairs, total_expected_rels)

    # --- kind accuracy, given the pair was found at all ---
    correct_kind_given_pair = matched_pairs - len(d.changed_relationships)
    kind_accuracy_given_correct_pair = _safe_div(correct_kind_given_pair, matched_pairs)

    return ScoreResult(
        class_recall=class_recall,
        class_precision=class_precision,
        class_f1=class_f1,
        member_f1=member_f1,
        relationship_f1=relationship_f1,
        pair_recall=pair_recall,
        kind_accuracy_given_correct_pair=kind_accuracy_given_correct_pair,
    )
