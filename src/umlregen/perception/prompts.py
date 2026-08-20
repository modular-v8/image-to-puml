"""Loads versioned prompt templates from `prompts/` and substitutes
variables into them. Prompt text lives in files, never inline strings --
that's what lets editing a template automatically invalidate exactly the
cache entries that used it, since the prompt's own content is part of the
cache key (see `perception/client.py`'s `cache_key`).
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(template_name: str, **variables: str) -> str:
    """Reads `prompts/{template_name}.txt` and substitutes `$variable`
    placeholders.

    Uses `string.Template` (`$var` / `${var}`), not `str.format`, because
    these prompts embed JSON Schema text -- literal `{`/`}` characters
    that `str.format` would misparse as format fields.

    The template's own filename argument is named `template_name`, not
    `name`, precisely so it can never collide with a real template
    variable legitimately called `$name`.
    """
    path = _PROMPTS_DIR / f"{template_name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt template named {template_name!r} at {path}")
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute(**variables)
