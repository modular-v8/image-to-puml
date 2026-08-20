"""Rendering tests against the real plantuml.jar/java/dot toolchain.

Skipped cleanly when java isn't on PATH, since these actually shell out.
"""

import shutil

import pytest

from umlregen.errors import RenderFailed
from umlregen.render.plantuml import render

requires_java = pytest.mark.skipif(
    shutil.which("java") is None, reason="java not available on PATH"
)

VALID_PUML = """@startuml
class Foo {
  +bar()
}
@enduml
"""

MALFORMED_PUML = """@startuml
class Foo {
  +bar()
THIS IS NOT VALID PLANTUML @@@@
@enduml
"""

_MAGIC = {
    "svg": b"<svg",
    "png": b"\x89PNG",
    "pdf": b"%PDF",
}


@requires_java
@pytest.mark.parametrize("fmt", ["svg", "png", "pdf"])
def test_render_produces_expected_format(tmp_path, fmt: str) -> None:
    out_path = tmp_path / f"diagram.{fmt}"

    result = render(VALID_PUML, fmt, out_path)

    assert result == out_path
    assert out_path.is_file()
    data = out_path.read_bytes()
    assert len(data) > 0
    assert _MAGIC[fmt] in data[:256]


@requires_java
def test_render_failed_preserves_source_and_stderr(tmp_path) -> None:
    out_path = tmp_path / "diagram.svg"

    with pytest.raises(RenderFailed) as exc_info:
        render(MALFORMED_PUML, "svg", out_path)

    error = exc_info.value
    assert error.puml_source == MALFORMED_PUML
    assert error.stderr.strip() != ""
    assert not out_path.exists()
