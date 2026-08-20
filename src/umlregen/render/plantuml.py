"""Renders PlantUML source to an image via the plantuml.jar subprocess.

Requires a JRE and Graphviz's ``dot`` on PATH (or located via env var / explicit
path) -- class diagram layout fails without ``dot``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from umlregen.errors import DependencyMissing, RenderFailed

RenderFormat = Literal["svg", "png", "pdf"]

_FORMAT_FLAGS: dict[str, str] = {"svg": "-tsvg", "png": "-tpng", "pdf": "-tpdf"}

_DEFAULT_JAR_CANDIDATES = (Path("tools/plantuml.jar"),)

_INSTALL_HINTS = {
    "java": (
        "Install a JRE -- e.g. `winget install --id EclipseAdoptium.Temurin.21.JRE` "
        "(Windows) or `apt install default-jre` (Linux) -- and ensure `java` is on PATH, "
        "or set UMLREGEN_JAVA to the executable path."
    ),
    "dot": (
        "Install Graphviz -- e.g. `winget install --id Graphviz.Graphviz` (Windows) or "
        "`apt install graphviz` (Linux) -- and ensure `dot` is on PATH, "
        "or set UMLREGEN_DOT to the executable path."
    ),
    "plantuml.jar": (
        "Download plantuml.jar from https://github.com/plantuml/plantuml/releases/latest "
        "and set UMLREGEN_PLANTUML_JAR to its path, or place it at tools/plantuml.jar."
    ),
}


def _locate_executable(name: str, env_var: str, configured: str | None) -> str:
    candidate = os.environ.get(env_var) or configured
    if candidate and shutil.which(candidate):
        return shutil.which(candidate)  # type: ignore[return-value]
    if candidate and Path(candidate).is_file():
        return candidate

    found = shutil.which(name)
    if found:
        return found

    raise DependencyMissing(
        f"Required tool '{name}' was not found "
        f"(checked ${env_var}, config, and PATH). {_INSTALL_HINTS[name]}"
    )


def _locate_jar(configured: str | None) -> str:
    candidate = os.environ.get("UMLREGEN_PLANTUML_JAR") or configured
    if candidate and Path(candidate).is_file():
        return candidate

    for default in _DEFAULT_JAR_CANDIDATES:
        if default.is_file():
            return str(default)

    raise DependencyMissing(
        "Required tool 'plantuml.jar' was not found "
        "(checked $UMLREGEN_PLANTUML_JAR, config, and the default tools/plantuml.jar). "
        f"{_INSTALL_HINTS['plantuml.jar']}"
    )


def preflight(
    java_path: str | None = None,
    dot_path: str | None = None,
    jar_path: str | None = None,
) -> dict[str, str]:
    """Locate java, dot, and plantuml.jar, or raise DependencyMissing.

    Each is checked env var, then the given config value, then PATH (java/dot)
    or a default location (the jar). Never invokes a subprocess itself, so a
    missing dependency is reported directly rather than surfacing as a
    subprocess traceback.
    """
    java = _locate_executable("java", "UMLREGEN_JAVA", java_path)
    dot = _locate_executable("dot", "UMLREGEN_DOT", dot_path)
    jar = _locate_jar(jar_path)
    return {"java": java, "dot": dot, "jar": jar}


def render(
    puml_text: str,
    fmt: RenderFormat,
    out_path: str | Path,
    *,
    java_path: str | None = None,
    dot_path: str | None = None,
    jar_path: str | None = None,
) -> Path:
    """Render PlantUML source to `fmt` (svg, png, or pdf) at `out_path`.

    Raises RenderFailed, preserving the source and PlantUML's stderr, if
    rendering fails -- e.g. malformed .puml syntax.
    """
    if fmt not in _FORMAT_FLAGS:
        raise ValueError(f"Unsupported render format: {fmt!r} (expected one of {sorted(_FORMAT_FLAGS)})")

    tools = preflight(java_path, dot_path, jar_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        source_file = tmp_dir_path / "diagram.puml"
        source_file.write_text(puml_text, encoding="utf-8")

        result = subprocess.run(
            [
                tools["java"],
                f"-DGRAPHVIZ_DOT={tools['dot']}",
                "-jar",
                tools["jar"],
                _FORMAT_FLAGS[fmt],
                "-failfast2",
                "-charset",
                "UTF-8",
                "-o",
                str(tmp_dir_path),
                str(source_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        generated_file = source_file.with_suffix(f".{fmt}")
        if result.returncode != 0 or not generated_file.is_file():
            raise RenderFailed(
                f"PlantUML failed to render to {fmt} (exit code {result.returncode})",
                puml_source=puml_text,
                stderr=result.stderr,
            )

        shutil.move(str(generated_file), str(out_path))
        return out_path
