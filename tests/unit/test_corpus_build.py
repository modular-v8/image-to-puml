"""Tests for T2.16's corpus build: reproducible regeneration, and at
least three visually distinct styles applied across the set. Requires
Java (it actually renders); skipped cleanly when absent."""

import shutil
from pathlib import Path

import pytest

from umlregen.eval.corpus import _STYLES, build_corpus

requires_java = pytest.mark.skipif(
    shutil.which("java") is None, reason="java not available on PATH"
)


def test_at_least_three_distinct_styles_defined() -> None:
    assert len(set(_STYLES)) >= 3


@requires_java
def test_corpus_build_is_reproducible(tmp_path: Path) -> None:
    ir_dir = Path("corpus/ir")

    run1_puml, run1_img = tmp_path / "puml1", tmp_path / "img1"
    build_corpus(ir_dir=ir_dir, puml_dir=run1_puml, img_dir=run1_img)

    run2_puml, run2_img = tmp_path / "puml2", tmp_path / "img2"
    build_corpus(ir_dir=ir_dir, puml_dir=run2_puml, img_dir=run2_img)

    puml_files_1 = sorted(run1_puml.glob("*.puml"))
    puml_files_2 = sorted(run2_puml.glob("*.puml"))
    assert [p.name for p in puml_files_1] == [p.name for p in puml_files_2]
    for file1, file2 in zip(puml_files_1, puml_files_2):
        assert file1.read_text(encoding="utf-8") == file2.read_text(encoding="utf-8")


@requires_java
def test_corpus_build_applies_at_least_three_distinct_styles(tmp_path: Path) -> None:
    ir_dir = Path("corpus/ir")
    puml_dir, img_dir = tmp_path / "puml", tmp_path / "img"

    written = build_corpus(ir_dir=ir_dir, puml_dir=puml_dir, img_dir=img_dir)

    assert len(written) >= 8  # T2.15's corpus size, carried through here
    puml_contents = {p.read_text(encoding="utf-8") for p in puml_dir.glob("*.puml")}
    # Different IRs produce different .puml regardless of style, so instead
    # check that each of the non-empty style blocks shows up verbatim in
    # at least one output -- proof the style was actually applied, not
    # just defined.
    applied = {style for style in _STYLES if style and any(style in c for c in puml_contents)}
    non_empty_styles = [s for s in _STYLES if s]
    assert applied == set(non_empty_styles)  # every non-empty style got used at least once
    assert len(applied) + 1 >= 3  # plus the "" (plain) style always present -> >= 3 total
