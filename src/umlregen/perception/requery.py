"""Targeted re-query (T3.21): re-ask about exactly one disagreement from
the verification loop's diff, over the whole image with a narrower
question -- not a crop. The conditional track (bounding boxes and
per-connector crops) is closed (tasks.md), so there is no reliable region
to crop to; a narrower *question* over the same full image is what's
available instead, and is still meaningfully narrower than a full
re-extraction.
"""

from __future__ import annotations

import json
from typing import Any

from umlregen.ir.models import Member, RelKind, Relationship
from umlregen.perception.client import VisionClient
from umlregen.perception.prompts import load_prompt
from umlregen.perception.repair import complete_with_repair

_MEMBER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "visibility": {"type": ["string", "null"], "enum": ["+", "-", "#", "~", None]},
        "name": {"type": "string"},
        "type": {"type": ["string", "null"]},
        "params": {"type": ["string", "null"]},
        "is_static": {"type": "boolean"},
        "is_abstract": {"type": "boolean"},
    },
    "required": ["name"],
}

_CLASS_MEMBERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "attributes": {"type": "array", "items": _MEMBER_SCHEMA},
        "methods": {"type": "array", "items": _MEMBER_SCHEMA},
    },
    "required": ["attributes", "methods"],
}

_RELATIONSHIP_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "relationship_exists": {"type": "boolean"},
        "kind": {"type": ["string", "null"], "enum": [k.value for k in RelKind] + [None]},
        "source_mult": {"type": ["string", "null"]},
        "target_mult": {"type": ["string", "null"]},
        "label": {"type": ["string", "null"]},
        "evidence": {"type": ["string", "null"]},
    },
    "required": ["relationship_exists"],
}


def requery_class_members(
    client: VisionClient, image: bytes, class_name: str
) -> tuple[list[Member], list[Member], float]:
    """Re-asks about exactly one class's members. Returns
    `(attributes, methods, cost_usd)`.
    """
    prompt = load_prompt(
        "verify_class_members",
        class_name=class_name,
        schema=json.dumps(_CLASS_MEMBERS_SCHEMA),
    )

    def validate(data: dict[str, Any], is_last_attempt: bool) -> tuple[list[Member], list[Member]]:
        attributes = [Member.model_validate(m) for m in data.get("attributes", [])]
        methods = [Member.model_validate(m) for m in data.get("methods", [])]
        return attributes, methods

    (attributes, methods), cost = complete_with_repair(
        client, image, prompt, _CLASS_MEMBERS_SCHEMA, validate
    )
    return attributes, methods, cost


# T3.24 found live, on real diagrams, that a narrower re-query is NOT
# inherently more reliable than the original extraction: a first version
# of this constant (0.6, above extract.py's 0.5 stage-B placeholder, on
# the theory that a single-purpose question is more trustworthy by
# construction) let a re-query silently overwrite three correct baseline
# relationships on `observer_pattern` with three wrong ones, because
# 0.6 >= 0.5 is true unconditionally -- T3.34's confidence guard was
# structurally unable to reject anything against real placeholder-
# confidence data, only against the artificially high confidence values
# the offline tests happened to construct.
#
# Deliberately BELOW _PLACEHOLDER_CONFIDENCE now: a re-query can rescue a
# relationship that already has no real confidence behind it (T3.41's
# degraded, no-evidence ones, or a genuinely missing relationship with no
# prior answer at all), but can never second-guess an original answer
# that was never flagged as uncertain in the first place. Verification's
# job is narrowed to "fix what's already known to be shaky", not
# "relitigate everything a re-render disagrees with".
REQUERY_CONFIDENCE = 0.3


def requery_relationship(
    client: VisionClient, image: bytes, source_name: str, target_name: str
) -> tuple[Relationship | None, float]:
    """Re-asks whether a relationship exists between exactly these two
    named classes. Returns `(relationship_or_None, cost_usd)` -- `None`
    means the re-query concluded no direct relationship exists.
    """
    prompt = load_prompt(
        "verify_relationship",
        source_name=source_name,
        target_name=target_name,
        schema=json.dumps(_RELATIONSHIP_QUERY_SCHEMA),
    )

    def validate(data: dict[str, Any], is_last_attempt: bool) -> Relationship | None:
        if not data.get("relationship_exists"):
            return None
        kind = data.get("kind")
        if kind not in {k.value for k in RelKind}:
            if not is_last_attempt:
                raise ValueError(
                    f"relationship_exists is true but kind {kind!r} is not a valid RelKind"
                )
            # Same principle as T3.41: a malformed answer on the last
            # attempt degrades to "not confirmed" rather than raising and
            # discarding -- the caller (loop.py) never deletes on an
            # unconfirmed answer, so this is safe by construction, not
            # just convenient.
            return None
        return Relationship(
            source=source_name,
            target=target_name,
            kind=RelKind(kind),
            source_mult=data.get("source_mult"),
            target_mult=data.get("target_mult"),
            label=data.get("label"),
            confidence=REQUERY_CONFIDENCE,
            evidence=data.get("evidence"),
        )

    result, cost = complete_with_repair(client, image, prompt, _RELATIONSHIP_QUERY_SCHEMA, validate)
    return result, cost
