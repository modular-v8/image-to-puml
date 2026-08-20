"""T1.16: class-block emission exercising every member variation. Visibility
markers are asserted directly against the generated .puml source (exact and
non-flaky) rather than parsed out of rendered SVG, since PlantUML re-styles
{static}/{abstract} as underline/italic on render rather than keeping the
literal markers as text."""

import shutil

import pytest

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Class, Diagram, Member
from umlregen.render.plantuml import render

requires_java = pytest.mark.skipif(
    shutil.which("java") is None, reason="java not available on PATH"
)


def _all_member_variations_diagram() -> Diagram:
    return Diagram(
        classes=[
            Class(
                id="Widget",
                name="Widget",
                kind="class",
                stereotype="Entity",
                attributes=[
                    Member(visibility="+", name="pub_attr", type="str"),
                    Member(visibility="-", name="priv_attr", type="int"),
                    Member(visibility="#", name="prot_attr", type="bool"),
                    Member(visibility="~", name="pkg_attr", type="float"),
                    Member(visibility="+", name="static_attr", type="int", is_static=True),
                ],
                methods=[
                    Member(visibility="+", name="pub_method", params="", type="void"),
                    Member(visibility="-", name="priv_method", params="x: int", type="bool"),
                    Member(
                        visibility="+",
                        name="abstract_method",
                        params="",
                        type="void",
                        is_abstract=True,
                    ),
                ],
            )
        ],
    )


def test_class_block_shows_every_visibility_marker() -> None:
    puml = ir_to_puml(_all_member_variations_diagram())
    assert "+pub_attr: str" in puml
    assert "-priv_attr: int" in puml
    assert "#prot_attr: bool" in puml
    assert "~pkg_attr: float" in puml


def test_class_block_shows_static_and_abstract_modifiers() -> None:
    puml = ir_to_puml(_all_member_variations_diagram())
    assert "+{static} static_attr: int" in puml
    assert "+{abstract} abstract_method(): void" in puml


def test_class_block_shows_stereotype() -> None:
    puml = ir_to_puml(_all_member_variations_diagram())
    assert "<<Entity>>" in puml


@requires_java
def test_class_block_with_every_member_variation_renders(tmp_path) -> None:
    puml = ir_to_puml(_all_member_variations_diagram())
    render(puml, "svg", tmp_path / "out.svg")
