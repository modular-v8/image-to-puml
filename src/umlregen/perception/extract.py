"""Two-stage extraction: stage A (classes) first, then stage B
(relationships) given stage A's class list as context. Two calls with a
narrower question each beats one call asking for everything at once --
see spec.md's prior decisions.

Both stages route through `complete_with_repair`: on a validation
failure -- malformed JSON, or JSON that fails the caller's own check --
the request is re-issued exactly once with the error appended to the
prompt, and only raises `ExtractionInvalid` if the retry also fails. The
repair-retry is the primary path here, not a defensive fallback: spec
flags that free vision models honour JSON-schema constraints unevenly.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from umlregen.errors import ExtractionDeclined
from umlregen.ir.models import Diagram
from umlregen.ir.schema import prompt_schema
from umlregen.perception.client import VisionClient
from umlregen.perception.prompts import load_prompt
from umlregen.perception.repair import complete_with_repair

_ID_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_]")

# T3.5: evidence strings the repair-retry treats as no better than empty --
# lazy non-answers a model might emit instead of describing what it saw.
# Deliberately narrow (exact match after casefold+strip) rather than a
# fuzzy quality classifier: false positives here would repair-retry a
# genuinely fine response, wasting a call for nothing.
_BOILERPLATE_EVIDENCE = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "see above",
    "see notation rubric",
    "not specified",
    "not applicable",
}

# Placeholder until Phase 3 builds real confidence scoring (the
# per-connector crop pass and verification-loop agreement -- both cut or
# shipped disabled; see README). The model is deliberately never asked
# for confidence -- schema.py prunes that field, since a self-reported
# number from the model would be meaningless -- so something has to
# assign one before `Relationship` (which has no default) can validate.
# T4.16 calibrated config.py's default threshold to 0.3, specifically
# *below* this value -- an ordinary relationship at this placeholder does
# NOT show up in review.md; only T3.41's degraded floor-confidence ones
# do. See config.py's DEFAULT_CONFIDENCE_THRESHOLD for the full reasoning.
_PLACEHOLDER_CONFIDENCE = 0.5

# T3.41: the floor a relationship gets when it survives to the end of the
# repair-retry with still no usable evidence. Below _PLACEHOLDER_CONFIDENCE
# deliberately -- a relationship the model never actually justified is
# less trustworthy than one it justified but for which we just don't have
# a real confidence signal yet, and review.md (T4.7) sorts on this.
_NO_EVIDENCE_CONFIDENCE = 0.0


def _derive_class_id(name: str, used_ids: set[str]) -> str:
    """A simple, deterministic id from a class name: sanitized name, or
    numerically suffixed on collision (e.g. two classes literally named
    the same thing in one response).

    Distinct from `generate/puml.py`'s PlantUML alias derivation -- id
    only needs to be unique within the diagram, not renderer-safe; the
    renderer-safe transformation happens later, from `name`, when
    generating `.puml`.
    """
    base = _ID_UNSAFE_CHARS.sub("_", name).strip("_") or "Class"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _assign_class_ids(classes_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_ids: set[str] = set()
    return [
        {**class_data, "id": _derive_class_id(class_data.get("name", ""), used_ids)}
        for class_data in classes_data
    ]


def extract_classes(client: VisionClient, image: bytes) -> tuple[Diagram, float]:
    """Stage A: whole image -> classes, members, visibility, stereotypes,
    kind. No relationships requested in this pass -- `relationships` is
    forced to `[]` regardless of what the model returns here.

    T4.19: a well-formed response reporting zero classes is not
    automatically accepted. T3.28 found six diagrams where the model
    returned complete, valid JSON with an empty class list and an
    explanatory warning, nowhere near the token cap -- a genuine decline,
    not a parse failure `complete_with_repair`'s retry can fix. On that
    outcome, this issues exactly one direct reframed retry (not routed
    through `complete_with_repair`, so it doesn't compound with that
    mechanism's own repair-retry); if the reframe also comes back empty,
    raises `ExtractionDeclined` rather than silently returning an empty
    diagram for a caller to (mis)treat as an ordinary empty result.
    """
    schema = prompt_schema()
    prompt = load_prompt("extract_classes", schema=json.dumps(schema))

    def validate(data: dict[str, Any], is_last_attempt: bool) -> Diagram:
        cleaned = dict(data)
        cleaned["classes"] = _assign_class_ids(cleaned.get("classes", []))
        cleaned["relationships"] = []
        return Diagram.normalize(cleaned)

    diagram, cost = complete_with_repair(client, image, prompt, schema, validate)
    if diagram.classes:
        return diagram, cost

    reframed_prompt = load_prompt("extract_classes_reframe", schema=json.dumps(schema))
    response = client.complete(image, reframed_prompt, schema=schema)
    total_cost = cost + response.cost_usd

    if isinstance(response.parsed_json, dict):
        try:
            retried = validate(response.parsed_json, True)
        except (ValueError, PydanticValidationError):
            retried = None
        if retried is not None and retried.classes:
            return retried, total_cost

    raise ExtractionDeclined(
        "Extraction reported zero classes both on the original attempt and "
        "after a reframed retry -- treating this as a genuine model decline, "
        "not a parse failure (see T3.28/T4.19).",
        raw_response=response.raw_text,
    )


def _format_class_list(diagram: Diagram) -> str:
    return "\n".join(f"- {cls.name}" for cls in diagram.classes)


def extract_relationships(
    client: VisionClient, image: bytes, classes: Diagram
) -> tuple[Diagram, float]:
    """Stage B: relationships only, given stage A's class list as context.
    Returns `classes` with `relationships` populated (and normalized, so a
    relationship referencing a name outside the stage A list is dropped
    with a warning rather than rejected outright).

    T3.41: empty/boilerplate evidence still routes through the repair-retry
    once, giving the model a real chance to describe what it saw -- but if
    the retry *also* comes back with no usable evidence, the affected
    relationship is kept at floor confidence with a warning, not discarded
    along with the rest of the diagram. Raising `ExtractionInvalid` over a
    missing description string, when the model otherwise read the diagram
    correctly, is exactly the failure-over-degradation spec.md's own
    principle forbids -- measured at ~12% of diagrams in Day 9b, with
    `media_library_icons` never producing a scoreable result at all under
    the old behavior. `ExtractionInvalid` is now reserved for what T2.12
    built it for: output that doesn't parse at all.
    """
    schema = prompt_schema()
    prompt = load_prompt(
        "extract_relationships",
        class_list=_format_class_list(classes),
        schema=json.dumps(schema),
    )
    name_to_id = {cls.name: cls.id for cls in classes.classes}

    def validate(data: dict[str, Any], is_last_attempt: bool) -> Diagram:
        relationships_data = []
        degradation_warnings = []
        for rel in data.get("relationships", []):
            rel = dict(rel)
            evidence = (rel.get("evidence") or "").strip().casefold()
            if evidence in _BOILERPLATE_EVIDENCE:
                if not is_last_attempt:
                    raise ValueError(
                        f"relationship {rel.get('source')!r} -> {rel.get('target')!r} "
                        f"({rel.get('kind')!r}) has empty or boilerplate evidence "
                        f"({rel.get('evidence')!r}); describe the actual line style "
                        "and arrowhead/diamond shape you saw"
                    )
                # Still no usable evidence after the repair-retry: degrade
                # this one relationship rather than lose the diagram.
                rel["confidence"] = _NO_EVIDENCE_CONFIDENCE
                degradation_warnings.append(
                    f"relationship {rel.get('source')!r} -> {rel.get('target')!r} "
                    f"({rel.get('kind')!r}) kept at floor confidence: no usable "
                    "evidence even after the repair-retry"
                )
            # Stage B answers with class *names* (it was only given names
            # as context); translate to the ids stage A already assigned.
            rel["source"] = name_to_id.get(rel.get("source"), rel.get("source"))
            rel["target"] = name_to_id.get(rel.get("target"), rel.get("target"))
            rel.setdefault("confidence", _PLACEHOLDER_CONFIDENCE)
            relationships_data.append(rel)

        cleaned = classes.model_dump()
        cleaned["relationships"] = relationships_data
        cleaned["warnings"] = [*cleaned.get("warnings", []), *degradation_warnings]
        return Diagram.normalize(cleaned)

    return complete_with_repair(client, image, prompt, schema, validate)
