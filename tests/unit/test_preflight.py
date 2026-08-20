"""Preflight tests: missing java, dot, or plantuml.jar each raise DependencyMissing
naming the right tool, without ever invoking a subprocess. All offline."""

import pytest

from umlregen.errors import DependencyMissing
from umlregen.render import plantuml


def _fake_which(available: set[str]):
    def which(name: str) -> str | None:
        return f"/fake/{name}" if name in available else None

    return which


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("UMLREGEN_JAVA", "UMLREGEN_DOT", "UMLREGEN_PLANTUML_JAR"):
        monkeypatch.delenv(var, raising=False)


def test_missing_java_raises_naming_java(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setattr(plantuml.shutil, "which", _fake_which(set()))

    with pytest.raises(DependencyMissing) as exc_info:
        plantuml.preflight()

    message = str(exc_info.value)
    assert "java" in message.lower()
    assert "JRE" in message


def test_missing_dot_raises_naming_graphviz(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setattr(plantuml.shutil, "which", _fake_which({"java"}))

    with pytest.raises(DependencyMissing) as exc_info:
        plantuml.preflight()

    message = str(exc_info.value)
    assert "Graphviz" in message
    assert "install" in message.lower()


def test_missing_jar_raises_naming_jar(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setattr(plantuml.shutil, "which", _fake_which({"java", "dot"}))
    monkeypatch.chdir(tmp_path)  # no tools/plantuml.jar here, unlike the repo root

    with pytest.raises(DependencyMissing) as exc_info:
        plantuml.preflight()

    message = str(exc_info.value)
    assert "plantuml.jar" in message
