"""IR tests: round-trip fidelity, the two structural invariants, normalize()'s
repair behavior, and the prompt schema projection. All offline."""

import pytest
from pydantic import ValidationError

from umlregen.ir.models import Diagram, RelKind
from umlregen.ir.schema import prompt_schema

VALID_DIAGRAM = {
    "name": "example",
    "classes": [
        {
            "id": "Animal",
            "name": "Animal",
            "kind": "class",
            "stereotype": None,
            "attributes": [
                {
                    "visibility": "+",
                    "name": "name",
                    "type": "str",
                    "params": None,
                    "is_static": False,
                    "is_abstract": False,
                }
            ],
            "methods": [
                {
                    "visibility": "+",
                    "name": "speak",
                    "type": "void",
                    "params": "",
                    "is_static": False,
                    "is_abstract": True,
                }
            ],
            "bbox": {"x": 10, "y": 10, "w": 100, "h": 50},
        },
        {
            "id": "Dog",
            "name": "Dog",
            "kind": "class",
            "stereotype": None,
            "attributes": [],
            "methods": [],
            "bbox": None,
        },
    ],
    "relationships": [
        {
            "source": "Dog",
            "target": "Animal",
            "kind": "inheritance",
            "source_mult": None,
            "target_mult": None,
            "label": None,
            "confidence": 0.95,
            "evidence": "solid line with hollow triangle pointing at Animal",
        }
    ],
    "notes": [{"text": "core hierarchy", "class_id": "Animal"}],
    "warnings": [],
}


def test_valid_diagram_round_trips_unchanged() -> None:
    diagram = Diagram.model_validate(VALID_DIAGRAM)
    assert diagram.model_dump() == VALID_DIAGRAM


def test_duplicate_class_id_fails_validation() -> None:
    data = {
        "classes": [
            {"id": "A", "name": "A", "kind": "class"},
            {"id": "A", "name": "A-duplicate", "kind": "class"},
        ],
    }
    with pytest.raises(ValidationError, match="duplicate Class.id"):
        Diagram.model_validate(data)


def test_dangling_relationship_fails_validation() -> None:
    data = {
        "classes": [{"id": "A", "name": "A", "kind": "class"}],
        "relationships": [
            {"source": "A", "target": "Ghost", "kind": "association", "confidence": 0.5}
        ],
    }
    with pytest.raises(ValidationError, match="does not reference"):
        Diagram.model_validate(data)


def test_normalize_drops_dangling_relationships_with_named_warnings() -> None:
    data = {
        "classes": [{"id": "A", "name": "A", "kind": "class"}],
        "relationships": [
            {"source": "A", "target": "A", "kind": "association", "confidence": 0.9},
            {"source": "A", "target": "Ghost1", "kind": "dependency", "confidence": 0.4},
            {"source": "Ghost2", "target": "A", "kind": "aggregation", "confidence": 0.4},
        ],
    }

    diagram = Diagram.normalize(data)

    assert len(diagram.relationships) == 1
    assert diagram.relationships[0].target == "A"
    assert len(diagram.warnings) == 2
    assert any("Ghost1" in w and "dependency" in w for w in diagram.warnings)
    assert any("Ghost2" in w and "aggregation" in w for w in diagram.warnings)


def test_normalize_still_rejects_duplicate_ids() -> None:
    data = {
        "classes": [
            {"id": "A", "name": "A", "kind": "class"},
            {"id": "A", "name": "A-duplicate", "kind": "class"},
        ],
    }
    with pytest.raises(ValidationError, match="duplicate Class.id"):
        Diagram.normalize(data)


def _find_title_keys(node: object) -> bool:
    if isinstance(node, dict):
        if "title" in node:
            return True
        return any(_find_title_keys(v) for v in node.values())
    if isinstance(node, list):
        return any(_find_title_keys(item) for item in node)
    return False


def test_prompt_schema_shape() -> None:
    schema = prompt_schema()

    assert "$defs" in schema
    assert "properties" in schema

    relkind_values = set(schema["$defs"]["RelKind"]["enum"])
    assert relkind_values == {kind.value for kind in RelKind}

    assert "bbox" not in schema["$defs"]["Class"]["properties"]
    assert "id" not in schema["$defs"]["Class"]["properties"]
    assert "confidence" not in schema["$defs"]["Relationship"]["properties"]

    assert not _find_title_keys(schema)
