"""T2.15: hand-authored corpus IR files, each small and focused on a
different axis of variation (inheritance depth, composition nesting,
member density, multiplicity richness, minimal case). Writes to
corpus/ir/*.json. Not part of the shipped package -- T2.16's `corpus
build` is the reproducible tool; this script is how the files were
authored in the first place.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from umlregen.ir.models import Class, Diagram, Member, RelKind, Relationship

diagrams: dict[str, Diagram] = {}

# --- animal_kingdom: inheritance depth (3-level chain), abstract class ---
diagrams["animal_kingdom"] = Diagram(
    name="animal_kingdom",
    classes=[
        Class(id="Animal", name="Animal", kind="abstract", attributes=[Member(name="name", type="str", visibility="#")]),
        Class(id="Mammal", name="Mammal", kind="abstract", attributes=[Member(name="furColor", type="str", visibility="#")]),
        Class(id="Dog", name="Dog", kind="class", attributes=[Member(name="breed", type="str", visibility="-")]),
        Class(id="DietType", name="DietType", kind="enum"),
    ],
    relationships=[
        Relationship(source="Mammal", target="Animal", kind=RelKind.INHERITANCE, confidence=1.0),
        Relationship(source="Dog", target="Mammal", kind=RelKind.INHERITANCE, confidence=1.0),
        Relationship(source="Animal", target="DietType", kind=RelKind.ASSOCIATION, confidence=1.0),
    ],
)

# --- vehicle_composition: nested composition (2 levels deep) ---
diagrams["vehicle_composition"] = Diagram(
    name="vehicle_composition",
    classes=[
        Class(id="Car", name="Car", kind="class", attributes=[Member(name="vin", type="str", visibility="-")]),
        Class(id="Engine", name="Engine", kind="class", attributes=[Member(name="horsepower", type="int", visibility="-")]),
        Class(id="Wheel", name="Wheel", kind="class"),
        Class(id="Piston", name="Piston", kind="class"),
    ],
    relationships=[
        Relationship(source="Car", target="Engine", kind=RelKind.COMPOSITION, confidence=1.0, source_mult="1", target_mult="1"),
        Relationship(source="Car", target="Wheel", kind=RelKind.COMPOSITION, confidence=1.0, source_mult="1", target_mult="4"),
        Relationship(source="Engine", target="Piston", kind=RelKind.COMPOSITION, confidence=1.0, source_mult="1", target_mult="4"),
    ],
)

# --- shape_hierarchy: realization-heavy, one interface / three implementors ---
diagrams["shape_hierarchy"] = Diagram(
    name="shape_hierarchy",
    classes=[
        Class(id="Drawable", name="Drawable", kind="interface", methods=[Member(name="draw", params="", type="void", visibility="+")]),
        Class(id="Circle", name="Circle", kind="class", attributes=[Member(name="radius", type="float", visibility="-")]),
        Class(id="Square", name="Square", kind="class", attributes=[Member(name="side", type="float", visibility="-")]),
        Class(id="Triangle", name="Triangle", kind="class", attributes=[Member(name="base", type="float", visibility="-"), Member(name="height", type="float", visibility="-")]),
    ],
    relationships=[
        Relationship(source="Circle", target="Drawable", kind=RelKind.REALIZATION, confidence=1.0),
        Relationship(source="Square", target="Drawable", kind=RelKind.REALIZATION, confidence=1.0),
        Relationship(source="Triangle", target="Drawable", kind=RelKind.REALIZATION, confidence=1.0),
    ],
)

# --- library_system: aggregation + association ---
diagrams["library_system"] = Diagram(
    name="library_system",
    classes=[
        Class(id="Library", name="Library", kind="class", attributes=[Member(name="name", type="str", visibility="-")]),
        Class(id="Book", name="Book", kind="class", attributes=[Member(name="isbn", type="str", visibility="-")]),
        Class(id="Member", name="Member", kind="class", attributes=[Member(name="memberId", type="str", visibility="-")]),
        Class(id="Author", name="Author", kind="class", attributes=[Member(name="name", type="str", visibility="-")]),
    ],
    relationships=[
        Relationship(source="Library", target="Book", kind=RelKind.AGGREGATION, confidence=1.0, source_mult="1", target_mult="0..*"),
        Relationship(source="Library", target="Member", kind=RelKind.AGGREGATION, confidence=1.0, source_mult="1", target_mult="0..*"),
        Relationship(source="Book", target="Author", kind=RelKind.ASSOCIATION, confidence=1.0, source_mult="*", target_mult="1"),
    ],
)

# --- notification_system: dependency-heavy + directed association ---
diagrams["notification_system"] = Diagram(
    name="notification_system",
    classes=[
        Class(id="NotificationService", name="NotificationService", kind="class", stereotype="Service"),
        Class(id="EmailSender", name="EmailSender", kind="class"),
        Class(id="SmsSender", name="SmsSender", kind="class"),
        Class(id="UserPreferences", name="UserPreferences", kind="class"),
    ],
    relationships=[
        Relationship(source="NotificationService", target="EmailSender", kind=RelKind.DEPENDENCY, confidence=1.0),
        Relationship(source="NotificationService", target="SmsSender", kind=RelKind.DEPENDENCY, confidence=1.0),
        Relationship(source="NotificationService", target="UserPreferences", kind=RelKind.DIRECTED_ASSOCIATION, confidence=1.0),
    ],
)

# --- minimal_pair: smallest possible case -- 2 bare classes, one relationship ---
diagrams["minimal_pair"] = Diagram(
    name="minimal_pair",
    classes=[
        Class(id="A", name="A", kind="class"),
        Class(id="B", name="B", kind="class"),
    ],
    relationships=[
        Relationship(source="A", target="B", kind=RelKind.ASSOCIATION, confidence=1.0),
    ],
)

# --- inventory_stereotypes: high member density, stereotypes, static/abstract ---
diagrams["inventory_stereotypes"] = Diagram(
    name="inventory_stereotypes",
    classes=[
        Class(
            id="Warehouse", name="Warehouse", kind="class", stereotype="Entity",
            attributes=[
                Member(name="id", type="str", visibility="-"),
                Member(name="location", type="str", visibility="-"),
                Member(name="capacity", type="int", visibility="-", is_static=False),
                Member(name="instanceCount", type="int", visibility="-", is_static=True),
            ],
            methods=[
                Member(name="addStock", params="item: StockItem", type="void", visibility="+"),
                Member(name="removeStock", params="item: StockItem", type="bool", visibility="+"),
                Member(name="create", params="", type="Warehouse", visibility="+", is_static=True),
            ],
        ),
        Class(
            id="StockItem", name="StockItem", kind="class", stereotype="ValueObject",
            attributes=[
                Member(name="sku", type="str", visibility="-"),
                Member(name="quantity", type="int", visibility="-"),
            ],
        ),
        Class(id="Status", name="Status", kind="enum"),
    ],
    relationships=[
        Relationship(source="Warehouse", target="StockItem", kind=RelKind.AGGREGATION, confidence=1.0, source_mult="1", target_mult="0..*"),
        Relationship(source="StockItem", target="Status", kind=RelKind.ASSOCIATION, confidence=1.0),
    ],
)

# --- team_project: multiplicity-rich, mixed kinds in one file ---
diagrams["team_project"] = Diagram(
    name="team_project",
    classes=[
        Class(id="Employee", name="Employee", kind="class", attributes=[Member(name="employeeId", type="str", visibility="-")]),
        Class(id="Manager", name="Manager", kind="class"),
        Class(id="Team", name="Team", kind="class"),
        Class(id="Project", name="Project", kind="class"),
    ],
    relationships=[
        Relationship(source="Manager", target="Employee", kind=RelKind.INHERITANCE, confidence=1.0),
        Relationship(source="Team", target="Employee", kind=RelKind.AGGREGATION, confidence=1.0, source_mult="1", target_mult="5..20"),
        Relationship(source="Employee", target="Project", kind=RelKind.ASSOCIATION, confidence=1.0, source_mult="*", target_mult="*"),
        Relationship(source="Team", target="Project", kind=RelKind.DIRECTED_ASSOCIATION, confidence=1.0, source_mult="1", target_mult="1..*"),
    ],
)

ir_dir = Path("corpus/ir")
ir_dir.mkdir(parents=True, exist_ok=True)

for filename, diagram in diagrams.items():
    path = ir_dir / f"{filename}.json"
    path.write_text(diagram.model_dump_json(indent=2), encoding="utf-8")
    kinds = sorted({rel.kind.value for rel in diagram.relationships})
    print(f"wrote {path} ({len(diagram.classes)} classes, {len(diagram.relationships)} rels, kinds={kinds})")
