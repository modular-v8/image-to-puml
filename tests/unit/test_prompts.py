"""Offline tests for the prompt loader (T2.9): templates load from disk
with variable substitution, and -- since the cache key hashes the prompt
text itself -- editing a template changes the cache key for any call that
uses it."""

from pathlib import Path

import pytest

from umlregen.perception.client import cache_key
from umlregen.perception.prompts import load_prompt


def test_loads_a_real_template_with_substitution() -> None:
    text = load_prompt("extract_classes", schema="{}")
    assert "{}" in text
    assert "$schema" not in text  # placeholder was substituted, not left literal


def test_missing_template_raises_clear_error() -> None:
    with pytest.raises(FileNotFoundError, match="no_such_prompt"):
        load_prompt("no_such_prompt")


def test_missing_variable_raises() -> None:
    with pytest.raises(KeyError):
        load_prompt("extract_classes")  # "schema" placeholder left unfilled


def test_curly_braces_in_substituted_json_are_not_mistaken_for_placeholders() -> None:
    # This is exactly why string.Template (not str.format) was chosen --
    # a JSON schema is full of literal { } that str.format would choke on.
    schema_text = '{"type": "object", "properties": {"name": {"type": "string"}}}'
    text = load_prompt("extract_classes", schema=schema_text)
    assert schema_text in text


def test_editing_a_prompt_file_changes_the_cache_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import umlregen.perception.prompts as prompts_module

    fake_prompts_dir = tmp_path
    monkeypatch.setattr(prompts_module, "_PROMPTS_DIR", fake_prompts_dir)

    (fake_prompts_dir / "greeting.txt").write_text("Hello, $name!", encoding="utf-8")
    prompt_v1 = load_prompt("greeting", name="World")
    key_v1 = cache_key(b"image-bytes", prompt_v1, "test/model", {})

    (fake_prompts_dir / "greeting.txt").write_text("Hi there, $name!", encoding="utf-8")
    prompt_v2 = load_prompt("greeting", name="World")
    key_v2 = cache_key(b"image-bytes", prompt_v2, "test/model", {})

    assert prompt_v1 != prompt_v2
    assert key_v1 != key_v2
