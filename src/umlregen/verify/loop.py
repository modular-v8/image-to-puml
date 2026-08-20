"""The verification loop (T3.20-T3.25, T3.34): render the extracted IR
back to an image, re-extract from that render, diff the re-extraction
against the original, and patch just the disagreements with a targeted
re-query -- not a full re-extraction. Promoted to unconditional (see
tasks.md's conditional-track closure): it helps every metric and needs
neither bounding boxes nor per-connector crops, unlike the cut track.

Scope, recorded here since it's a judgment call and not spelled out in
the acceptance criteria: whole-class add/remove disagreements (a class
present in one side of the diff but not the other) are not re-queried --
`requery_class_members` assumes the class exists in the image, which
doesn't cleanly fit "does this class exist at all". Only within-class
member disagreements (`changed_classes`) and relationship disagreements
(`changed_relationships`, `added_relationships`, `removed_relationships`)
are targeted.

T3.34's confidence guard is deliberately conservative on relationships:
a re-query can *add* a relationship the original missed, or *update* one
whose kind the original may have gotten wrong -- both gated on the
re-query's confidence being at least the original's (or, for an addition,
simply being confirmed at all, since there's no prior confidence to beat).
It never *removes* a relationship the original had, even when the
re-extraction disagrees and the re-query doesn't confirm it either --
there's no confidence signal on a negative re-query answer to weigh
against what's already there, so the safer default is to leave it. This
means the loop can only add information or raise its own confidence in
what it already had, never quietly delete something on a single
unconfident second opinion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.diff import DiagramDiff, diff, normalize_name
from umlregen.ir.models import Class, Diagram, Relationship
from umlregen.perception.client import VisionClient
from umlregen.perception.extract import extract_classes, extract_relationships
from umlregen.perception.requery import REQUERY_CONFIDENCE, requery_class_members, requery_relationship
from umlregen.render.plantuml import render

DEFAULT_MAX_ROUNDS = 2


@dataclass
class VerifyStats:
    """Cost/latency instrumentation (T3.23), split by stage."""

    rounds_run: int = 0
    converged: bool = False  # True: a round produced no diff. False: hit the round cap.
    render_reextract_calls: int = 0  # stage A + stage B calls, across all rounds
    requery_calls: int = 0
    rejected_patches: list[str] = field(default_factory=list)
    render_reextract_cost_usd: float = 0.0
    requery_cost_usd: float = 0.0
    latency_seconds: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        return self.render_reextract_cost_usd + self.requery_cost_usd

    @property
    def total_calls(self) -> int:
        return self.render_reextract_calls + self.requery_calls


@dataclass
class VerifyResult:
    diagram: Diagram
    stats: VerifyStats


def _render_and_reextract(
    diagram: Diagram, client: VisionClient, debug_dir: Path, round_index: int
) -> tuple[Diagram, bytes, float]:
    """Renders `diagram` and re-extracts from that render. The render
    lands in `debug_dir`, never the output directory -- spec's
    verification-diffs-structures-not-pictures decision means this image
    is a debugging artifact, not a deliverable.
    """
    puml_text = ir_to_puml(diagram)
    debug_dir.mkdir(parents=True, exist_ok=True)
    render_path = debug_dir / f"verify_round_{round_index}.png"
    render(puml_text, "png", render_path)
    image_bytes = render_path.read_bytes()

    stage_a, cost_a = extract_classes(client, image_bytes)
    reextracted, cost_b = extract_relationships(client, image_bytes, stage_a)
    return reextracted, image_bytes, cost_a + cost_b


def _find_class(diagram: Diagram, normalized_name: str) -> Class | None:
    for cls in diagram.classes:
        if normalize_name(cls.name) == normalized_name:
            return cls
    return None


def _find_relationship(diagram: Diagram, source_id: str, target_id: str) -> Relationship | None:
    for rel in diagram.relationships:
        if rel.source == source_id and rel.target == target_id:
            return rel
    return None


def _apply_targeted_requeries(
    diagram: Diagram,
    diagram_diff: DiagramDiff,
    image: bytes,
    client: VisionClient,
    stats: VerifyStats,
) -> Diagram:
    """One re-query per disagreement in `diagram_diff`, patching a copy
    of `diagram`. Returns the patched diagram; `diagram` itself is
    untouched.
    """
    patched = diagram.model_copy(deep=True)
    name_to_id = {normalize_name(c.name): c.id for c in patched.classes}

    for change in diagram_diff.changed_classes:
        cls = _find_class(patched, normalize_name(change.name))
        if cls is None:
            continue
        attributes, methods, cost = requery_class_members(client, image, cls.name)
        stats.requery_calls += 1
        stats.requery_cost_usd += cost
        # No confidence concept exists for members (ir/models.py) -- the
        # narrower, single-purpose question always replaces what's there.
        cls.attributes = attributes
        cls.methods = methods

    relationship_pairs = {
        (source, target)
        for source, target in (
            (rc.source, rc.target) for rc in diagram_diff.changed_relationships
        )
    }
    relationship_pairs |= {(s, t) for s, t, _ in diagram_diff.added_relationships}
    relationship_pairs |= {(s, t) for s, t, _ in diagram_diff.removed_relationships}

    for source_norm, target_norm in sorted(relationship_pairs):
        source_id = name_to_id.get(source_norm)
        target_id = name_to_id.get(target_norm)
        if source_id is None or target_id is None:
            continue  # a class this pair references no longer exists in `patched`
        source_cls = next(c for c in patched.classes if c.id == source_id)
        target_cls = next(c for c in patched.classes if c.id == target_id)

        existing = _find_relationship(patched, source_id, target_id)
        pair_label = f"{source_cls.name!r} -> {target_cls.name!r}"

        if existing is not None and existing.confidence >= REQUERY_CONFIDENCE:
            # T3.24: no call spent here. An original answer that already
            # carries real (non-degraded) confidence can never be beaten
            # by a re-query at this fixed confidence, so asking would
            # only spend a call on a patch that's rejected by
            # construction -- skip straight to that outcome.
            continue

        new_rel, cost = requery_relationship(client, image, source_cls.name, target_cls.name)
        stats.requery_calls += 1
        stats.requery_cost_usd += cost

        if new_rel is None:
            # Re-query found nothing. If the original had a relationship
            # here, leave it -- see the module docstring on why a
            # negative re-query answer never deletes (T3.34).
            continue

        new_rel.source = source_id
        new_rel.target = target_id

        if existing is None:
            # Nothing to be "at least as confident as" -- a confirmed
            # addition is always eligible.
            patched.relationships.append(new_rel)
            continue

        if new_rel.confidence < existing.confidence:
            stats.rejected_patches.append(
                f"{pair_label} ({existing.kind.value} -> {new_rel.kind.value}): "
                f"re-query confidence {new_rel.confidence} < existing {existing.confidence}, kept original"
            )
            continue

        existing.kind = new_rel.kind
        existing.source_mult = new_rel.source_mult
        existing.target_mult = new_rel.target_mult
        existing.label = new_rel.label
        existing.confidence = new_rel.confidence
        existing.evidence = new_rel.evidence

    return patched


def verify(
    diagram: Diagram,
    client: VisionClient,
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    debug_dir: Path | None = None,
) -> VerifyResult:
    """Runs the verification loop: render, re-extract, diff, targeted
    re-query, repeat -- stopping when a round produces no diff (T3.22,
    converged) or after `max_rounds` regardless (T3.22, cap).
    """
    debug_dir = debug_dir if debug_dir is not None else Path(".cache/verify_debug")
    stats = VerifyStats()
    current = diagram
    started_at = time.monotonic()

    for round_index in range(1, max_rounds + 1):
        reextracted, image_bytes, cost = _render_and_reextract(current, client, debug_dir, round_index)
        stats.render_reextract_calls += 2  # stage A + stage B, one call each
        stats.render_reextract_cost_usd += cost
        stats.rounds_run = round_index

        round_diff = diff(current, reextracted)
        if round_diff.is_empty:
            stats.converged = True
            break

        current = _apply_targeted_requeries(current, round_diff, image_bytes, client, stats)

    stats.latency_seconds = time.monotonic() - started_at
    return VerifyResult(diagram=current, stats=stats)
