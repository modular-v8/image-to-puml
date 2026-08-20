"""Projects the Pydantic IR to a JSON Schema suitable for embedding in a
vision-model prompt.

Things stripped relative to `Diagram.model_json_schema()`:
- `title`, which Pydantic auto-generates on every model and field and which
  is pure noise in a prompt.
- `bbox` (on `Class`) and `confidence` (on `Relationship`) -- fields the
  model must never populate, since bbox grounding and confidence scoring
  happen elsewhere in the pipeline, not as something the model self-reports.
- `id` (on `Class`) -- plan.md's data model describes it as "derived from
  the name", i.e. code-assigned (see `extract.py`'s id derivation), not
  something to ask a vision model to invent. Asking for it would also risk
  the model producing unstable or colliding ids across a repair-retry.
"""

from __future__ import annotations

import copy
from typing import Any

from umlregen.ir.models import Diagram

_FORBIDDEN_FIELDS: dict[str, set[str]] = {
    "Class": {"bbox", "id"},
    "Relationship": {"confidence"},
}


def _strip_titles(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _strip_titles(value) for key, value in node.items() if key != "title"}
    if isinstance(node, list):
        return [_strip_titles(item) for item in node]
    return node


def _prune_forbidden_fields(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs", {})
    for model_name, forbidden in _FORBIDDEN_FIELDS.items():
        model_schema = defs.get(model_name)
        if model_schema is None:
            continue
        properties = model_schema.get("properties", {})
        for field in forbidden:
            properties.pop(field, None)
        required = model_schema.get("required")
        if required:
            model_schema["required"] = [r for r in required if r not in forbidden]
    return schema


def prompt_schema() -> dict[str, Any]:
    """A JSON Schema for `Diagram`, ready to embed in a prompt."""
    schema = copy.deepcopy(Diagram.model_json_schema())
    schema = _prune_forbidden_fields(schema)
    schema = _strip_titles(schema)
    return schema
