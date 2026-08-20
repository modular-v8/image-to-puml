"""T1.21: emission robustness -- keyword-colliding names, names with spaces
and punctuation, empty member lists, and a class with no relationships all
must emit .puml that renders without error."""

import shutil

import pytest

from umlregen.generate.puml import ir_to_puml
from umlregen.ir.models import Class, Diagram
from umlregen.render.plantuml import render

requires_java = pytest.mark.skipif(
    shutil.which("java") is None, reason="java not available on PATH"
)


@requires_java
def test_keyword_colliding_class_name_renders(tmp_path) -> None:
    diagram = Diagram(classes=[Class(id="C1", name="class", kind="class")])
    render(ir_to_puml(diagram), "svg", tmp_path / "out.svg")


@requires_java
def test_name_with_spaces_and_punctuation_renders(tmp_path) -> None:
    diagram = Diagram(classes=[Class(id="C1", name='Order Item! (v2)"', kind="class")])
    render(ir_to_puml(diagram), "svg", tmp_path / "out.svg")


@requires_java
def test_empty_member_lists_render(tmp_path) -> None:
    diagram = Diagram(
        classes=[Class(id="C1", name="Empty", kind="class", attributes=[], methods=[])]
    )
    render(ir_to_puml(diagram), "svg", tmp_path / "out.svg")


@requires_java
def test_class_with_no_relationships_renders(tmp_path) -> None:
    diagram = Diagram(
        classes=[
            Class(id="A", name="A", kind="class"),
            Class(id="B", name="B", kind="class"),
        ],
        relationships=[],
    )
    render(ir_to_puml(diagram), "svg", tmp_path / "out.svg")
