"""Offline tests for extraction (T2.14) against real recorded fixtures --
committed responses from the live provider (google/gemma-4-26b-a4b-it,
paid tier per T3.36's evaluation-instrument decision, against
tests/fixtures/ecommerce_checkout.png), replayed via FakeVisionClient. No
network, no API key.

The test image is a dedicated copy under tests/fixtures/, deliberately
NOT corpus/img/ecommerce_checkout.png -- that path is legitimately
overwritten by T2.16's build_corpus() with a restyled render, which
silently broke these fixtures once already (different image bytes -> a
different cache key -> "fixture not found"). Keeping this image separate
means a corpus rebuild can never do that again.

Repair-retry itself is covered in test_extract_repair.py (a scripted
client gives tighter control over the malformed/valid response sequence
than a recorded fixture pair would), and NoClassesFound is covered in
test_api.py. Not duplicated here.
"""

from pathlib import Path

from umlregen.perception.client import FakeVisionClient
from umlregen.perception.extract import extract_classes, extract_relationships

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
_MODEL_ID = "google/gemma-4-26b-a4b-it"
_IMAGE_PATH = _FIXTURES_DIR / "ecommerce_checkout.png"

_EXPECTED_CLASS_NAMES = {
    "CreditCard",
    "Customer",
    "Person",
    "Order",
    "PaymentGateway",
    "PaymentMethod",
    "OrderLine",
    "Product",
}


def _fake_client() -> FakeVisionClient:
    return FakeVisionClient(model_id=_MODEL_ID, fixtures_dir=_FIXTURES_DIR)


def test_stage_a_shape_against_recorded_fixture() -> None:
    image_bytes = _IMAGE_PATH.read_bytes()

    diagram, cost = extract_classes(_fake_client(), image_bytes)

    assert {cls.name for cls in diagram.classes} == _EXPECTED_CLASS_NAMES
    assert diagram.relationships == []
    assert cost > 0.0  # recorded against the paid tier (T3.36); FakeVisionClient replays the real recorded cost


def test_stage_b_referential_integrity_against_recorded_fixture() -> None:
    image_bytes = _IMAGE_PATH.read_bytes()
    client = _fake_client()

    stage_a, _ = extract_classes(client, image_bytes)
    full, _ = extract_relationships(client, image_bytes, stage_a)

    assert len(full.relationships) == 6
    known_ids = {cls.id for cls in full.classes}
    for rel in full.relationships:
        assert rel.source in known_ids
        assert rel.target in known_ids
        assert rel.evidence  # required, non-empty per T2.11
    assert full.warnings == []  # nothing was dropped as a dangling reference
