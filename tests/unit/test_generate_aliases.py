"""Alias-derivation properties from T1.15's stated acceptance: distinctness
and order-independence. Fast, offline -- no rendering involved."""

from umlregen.generate.puml import derive_aliases
from umlregen.ir.models import Class


def test_case_differing_names_get_distinct_aliases() -> None:
    classes = [
        Class(id="C1", name="Order", kind="class"),
        Class(id="C2", name="order", kind="class"),
    ]
    aliases = derive_aliases(classes)
    assert aliases["C1"] != aliases["C2"]


def test_identical_names_get_distinct_suffixed_aliases() -> None:
    classes = [
        Class(id="C1", name="Order", kind="class"),
        Class(id="C2", name="Order", kind="class"),
    ]
    aliases = derive_aliases(classes)
    assert aliases["C1"] != aliases["C2"]


def test_alias_assignment_is_independent_of_input_order() -> None:
    a = Class(id="A", name="Alpha", kind="class")
    b = Class(id="B", name="Beta", kind="class")
    assert derive_aliases([a, b]) == derive_aliases([b, a])
