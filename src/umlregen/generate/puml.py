"""Pure IR -> PlantUML generation. No I/O, no model, no config.

`ir_to_puml` is deterministic: the same `Diagram`, regardless of the order
its `classes` and `relationships` lists happen to be in, always produces
byte-identical output. That's load-bearing for the spec's repeat-run
guarantee, and it's why aliasing and ordering both sort by a stable key
instead of trusting input order.
"""

from __future__ import annotations

import re

from umlregen.ir.models import Class, Diagram, Member, RelKind, Relationship

_SAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9_]")

# Alias tokens that would be ambiguous or reserved if used bare in PlantUML
# source. Not exhaustive of every PlantUML keyword -- just the ones that
# plausibly collide with a class name plucked from a real diagram.
_RESERVED_ALIASES = {
    "class", "interface", "abstract", "enum", "package", "namespace",
    "note", "as", "extends", "implements", "hide", "show", "skinparam",
    "left", "right", "top", "bottom", "of", "on", "title", "header",
    "footer", "legend", "endlegend", "start", "stop", "state", "object",
}

_KIND_KEYWORDS = {
    "class": "class",
    "interface": "interface",
    "abstract": "abstract class",
    "enum": "enum",
}

_REL_ARROWS = {
    RelKind.INHERITANCE: "--|>",
    RelKind.REALIZATION: "..|>",
    RelKind.COMPOSITION: "*--",
    RelKind.AGGREGATION: "o--",
    RelKind.ASSOCIATION: "--",
    RelKind.DIRECTED_ASSOCIATION: "-->",
    RelKind.DEPENDENCY: "..>",
}


def _sanitize_identifier(raw: str) -> str:
    ident = _SAFE_CHAR_RE.sub("_", raw).strip("_")
    if not ident:
        ident = "C"
    if ident[0].isdigit():
        ident = f"C_{ident}"
    return ident


def derive_aliases(classes: list[Class]) -> dict[str, str]:
    """Maps each `Class.id` to a stable, collision-free PlantUML alias.

    Deterministic regardless of input order: classes are processed sorted
    by (name, id) rather than by their position in the list, so suffix
    assignment on a collision never depends on which class happened to
    come first in the input.
    """
    ordered = sorted(classes, key=lambda c: (c.name, c.id))
    used: set[str] = set()
    aliases: dict[str, str] = {}
    for cls in ordered:
        base = _sanitize_identifier(cls.name)
        if base.lower() in _RESERVED_ALIASES:
            base = f"{base}_"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        aliases[cls.id] = candidate
    return aliases


def _escape_display_name(name: str) -> str:
    # PlantUML's quoted display-name syntax has no working backslash-escape
    # for an embedded literal quote (empirically confirmed: it renders the
    # backslash literally rather than escaping). Dropping the character is
    # simpler and safer than a broken escape, and real class names don't
    # contain literal quote characters anyway.
    return name.replace('"', "")


def _format_modifiers(member: Member) -> str:
    mods = []
    if member.is_static:
        mods.append("{static}")
    if member.is_abstract:
        mods.append("{abstract}")
    return " ".join(mods) + (" " if mods else "")


def _format_attribute(member: Member) -> str:
    marker = member.visibility or ""
    signature = member.name
    if member.type:
        signature += f": {member.type}"
    return f"{marker}{_format_modifiers(member)}{signature}"


def _format_method(member: Member) -> str:
    marker = member.visibility or ""
    signature = f"{member.name}({member.params or ''})"
    if member.type:
        signature += f": {member.type}"
    return f"{marker}{_format_modifiers(member)}{signature}"


def _emit_class_block(cls: Class, alias: str) -> str:
    keyword = _KIND_KEYWORDS[cls.kind]
    header = f'{keyword} "{_escape_display_name(cls.name)}" as {alias}'
    if cls.stereotype:
        header += f" <<{cls.stereotype}>>"

    if not cls.attributes and not cls.methods:
        return header

    lines = [header + " {"]
    for attr in cls.attributes:
        lines.append(f"  {_format_attribute(attr)}")
    if cls.attributes and cls.methods:
        lines.append("  --")
    for method in cls.methods:
        lines.append(f"  {_format_method(method)}")
    lines.append("}")
    return "\n".join(lines)


def _emit_relationship_line(rel: Relationship, aliases: dict[str, str]) -> str:
    parts = [aliases[rel.source]]
    if rel.source_mult:
        parts.append(f'"{rel.source_mult}"')
    parts.append(_REL_ARROWS[rel.kind])
    if rel.target_mult:
        parts.append(f'"{rel.target_mult}"')
    parts.append(aliases[rel.target])

    line = " ".join(parts)
    if rel.label:
        line += f" : {rel.label}"
    return line


# T4.8: a small, tasteful default -- readability only, never a color
# scheme opinion (that's what eval/corpus.py's own style rotation is for,
# deliberately kept separate; see its module docstring). Off by default,
# so the golden-file/determinism tests written against the plain output
# keep passing unchanged.
_THEME_BLOCK = "skinparam shadowing false\nskinparam roundCorner 8\n"


def _build_lines(
    diagram: Diagram, *, model_id: str | None, include_theme: bool
) -> tuple[list[str], dict[int, int]]:
    """The one place `.puml` lines are actually assembled -- both
    `ir_to_puml` and `ir_to_puml_with_line_map` call this with identical
    arguments, so line numbers computed here always match what actually
    gets written to disk, header and theme block included, never a
    second implementation that could quietly drift apart.

    `model_id` is deliberately the only run-specific header field --
    T4.10 requires two warm-cache runs on the same image to produce
    byte-identical `.puml`, and a generation *date* would break that the
    moment the same cached result is written out on two different
    calendar days. Omitted entirely rather than an unstable "freeze"
    mechanism this project has no existing infrastructure to support.

    Returns the emitted lines and a map from each relationship's `id()`
    (object identity -- safe here since callers pass the same
    `Relationship` instances they'll later look up by) to its 1-indexed
    line number.
    """
    aliases = derive_aliases(diagram.classes)
    ordered_classes = sorted(diagram.classes, key=lambda c: (c.name, c.id))
    ordered_relationships = sorted(
        diagram.relationships,
        key=lambda r: (
            aliases[r.source],
            aliases[r.target],
            r.kind.value,
            r.label or "",
            r.source_mult or "",
            r.target_mult or "",
        ),
    )

    lines = ["@startuml"]
    if model_id is not None:
        lines.append(f"' Generated by uml-regen (model: {model_id})")
    lines.append("skinparam classAttributeIconSize 0")
    if include_theme:
        lines.extend(_THEME_BLOCK.splitlines())

    if ordered_classes:
        lines.append("")
        lines.append("' --- Classes ---")
        for cls in ordered_classes:
            lines.append(_emit_class_block(cls, aliases[cls.id]))

    line_map: dict[int, int] = {}
    if ordered_relationships:
        lines.append("")
        lines.append("' --- Relationships ---")
        for rel in ordered_relationships:
            lines.append(_emit_relationship_line(rel, aliases))
            line_map[id(rel)] = len(lines)  # 1-indexed: position just written

    lines.append("@enduml")
    return lines, line_map


def ir_to_puml(diagram: Diagram, *, model_id: str | None = None, include_theme: bool = False) -> str:
    """Renders `diagram` to deterministic PlantUML source.

    `model_id` (default `None`) adds a one-line generated-by comment
    naming the model; `include_theme` (default `False`) adds a small
    readability skinparam block. Both off by default so existing callers
    and golden-file tests see byte-identical output to before T4.8.
    """
    lines, _ = _build_lines(diagram, model_id=model_id, include_theme=include_theme)
    return "\n".join(lines) + "\n"


def ir_to_puml_with_line_map(
    diagram: Diagram, *, model_id: str | None = None, include_theme: bool = False
) -> tuple[str, dict[int, int]]:
    """Same output as `ir_to_puml` (same defaults, same parameters --
    pass the *same* arguments here as were used for the `.puml` actually
    written to disk), plus a map from each relationship object's `id()`
    to its 1-indexed line number in that output. What `generate/review.py`
    needs to cite a correct `.puml:N` for a low-confidence relationship.
    """
    lines, line_map = _build_lines(diagram, model_id=model_id, include_theme=include_theme)
    return "\n".join(lines) + "\n", line_map
