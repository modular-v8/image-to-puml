# Holdout corpus — provenance and licensing

Built for T3.26 (Phase 3, Day 7), expanded under T3.40 (Day 9b) once n=4 was judged too small to carry the conditional-track decision it had driven. Never used to develop or tune prompts.

Six of the eight are real diagrams from public sources with permissive licences (below); two are self-generated after a check-in (2026-08-18) found that publicly available diagrams with icon-style visibility markers under a clean licence weren't findable in reasonable time, and two candidate sources (freeprojectz.com, Creately's example gallery) were rejected outright — no stated licence on the former, explicit "all rights reserved" on the latter. Self-generation is a deliberate, recorded deviation from "hand-labelled from public sources" for those two files only; it keeps the corpus honestly licensed at the cost of testing two of eight diagrams on inputs the pipeline's own tooling produced. The synthetic-corpus overfitting risk this holdout exists to catch is checked by the six real, non-PlantUML diagrams.

## Real, publicly sourced (6 of 8)

### `wikipedia_domain_model` (`wikipedia_domain_model.png`)
- **Source**: [File:Class Diagram Wikipedia Wikipedia.class.png](https://commons.wikimedia.org/wiki/File:Class_Diagram_Wikipedia_Wikipedia.class.png), Wikimedia Commons.
- **Author**: BenTels (Dutch Wikipedia), 2004.
- **Licence**: Public domain, dedicated by the copyright holder.
- **Tool**: MagicDraw (NoMagic) — not PlantUML.
- **Why chosen**: non-PlantUML visual style, an interface, a package grouping the IR schema doesn't model (deliberately dropped, see below), a floating note, and a relationship whose kind is stated only in text ("Aggregatie") with no diamond glyph drawn.
- **Judgment calls**: class `name` fields keep the tool's literal header text verbatim (`Interface I0`, `Klasse K0`, `Klasse K1`, `Hulpklasse HK0`) rather than stripping the Dutch keyword prefix — reversed after the first T3.27 run (below) once it became clear that was the wrong call. The `Package P0` container is not represented as a `Class` — the IR schema has no package concept yet (see tasks.md T4.9) — so `K0`/`K1` appear as ordinary classes with no package membership, matching what the extractor itself will also be unable to capture. The K1–HK0 edge carries three overlapping text labels in the source (`Heeft`, `Aggregatie`, `Wordt gebruikt`); `Aggregatie` was kept as `label` since it most directly names the relationship, the two role names are dropped (unmodelled). The attached `Noot` note is anchored to that relationship, not a class; since `Note.class_id` only supports class attachment, it's recorded as a floating note.
- **Corrected after the first T3.27 run**: the initial version of this file (a) stripped "Interface"/"Klasse"/"Hulpklasse" from every class name on the theory that they're display keywords rather than part of the name, and (b) attributed the K0/K1 → I0 realization to `K1`, on the strength of a method-signature match. Both were wrong. (a) caused a spurious 0% class recall on the first live run, since the model reasonably reported the literal header text ("Klasse K0") and the scorer's exact-match name comparison doesn't forgive an editorial trim it has no way to know about. (b) was caught by disagreement with the model's own (correct) answer: a closer zoom shows the dashed realization line originates at `K0`'s box, not `K1`'s, and only routes along the package's top-right corner before turning up to `I0` — signature-matching was a plausible-sounding shortcut that turned out to be wrong. Both are fixed in the shipped file; this note is kept as a record that the correction happened and why, not as a live discrepancy.

### `visitor_pattern` (`visitor_pattern.png`)
- **Source**: [File:Visitor UML class diagram.svg](https://commons.wikimedia.org/wiki/File:Visitor_UML_class_diagram.svg), Wikimedia Commons.
- **Author**: Giacomo Ritucci, 2006.
- **Licence**: Dual GNU Free Documentation License v1.2+ and CC BY-SA 3.0 Unported. Attribution: Giacomo Ritucci.
- **Tool**: Omondo (Eclipse UML plugin), edited in Inkscape — not PlantUML.
- **Note on the shipped image**: the original is an SVG, outside spec's PNG/JPG input scope; `visitor_pattern.png` is a faithful rasterisation of that SVG (via `svglib`/`reportlab`, no content changes) done to produce a valid input format, not a redraw.
- **Why chosen**: the classic GoF Visitor pattern — realization, dependency, and an aggregation read from a role name ("collection") rather than a diamond glyph — plus overloaded methods shown without distinguishing signatures and four notes attached to specific methods (collapsed to their owning class, since `Note` has no method-level attachment).
- **Judgment calls**: member visibility is recorded as `null` throughout. Omondo renders small coloured icon badges per member, but which colour maps to which visibility level isn't documented anywhere findable, and guessing would risk injecting wrong ground truth into a metric (member F1) the project already measures — safer to record "not determinable" than a guess presented as fact. This means the diagram does **not** count toward the icon-visibility requirement below, despite using icons; only diagrams whose icon meaning is verified against a known convention count. The `ObjectStructure`–`Element` edge is recorded as `aggregation` on the strength of the "collection" role name and the standard textbook shape of this pattern, even though the rendered arrow end is an unresolved glyph (likely a mis-rendered diamond) rather than a clean diamond — recorded as a judgment call, not a certainty.

### `observer_pattern` (`observer_pattern.jpg`)
- **Source**: [File:Observer-pattern-uml.jpg](https://commons.wikimedia.org/wiki/File:Observer-pattern-uml.jpg), Wikimedia Commons.
- **Author**: Alexvaughan, 2005; edited by IanCarter and ChongDae.
- **Licence**: Dual CC BY-SA 3.0 Unported and GNU Free Documentation License v1.2+.
- **Tool**: not stated — genuine JPEG, not PlantUML.
- **Why chosen**: a second real, non-self-generated compressed screenshot (JPEG, 641×268) alongside the self-generated one below, plus a note attached to a class and an aggregation stated only via a role-labelled hollow diamond (`Subject` aggregates `* (ObserverCollection)` of `Observer`).
- **Judgment calls**: `Observer`'s box carries no `<<interface>>` stereotype or italics despite functioning as one in the GoF pattern; recorded as `kind: "class"` to match what's literally drawn, not the pattern's textbook semantics. Member visibility is `null` throughout — no markers are shown at all.

### `factory_method_pattern` (`factory_method_pattern.png`)
- **Source**: [File:Factory Method UML class diagram.svg](https://commons.wikimedia.org/wiki/File:Factory_Method_UML_class_diagram.svg), Wikimedia Commons.
- **Author**: Trashtoy, 2006.
- **Licence**: Public domain, dedicated by the copyright holder.
- **Tool**: hand-coded in a text editor — not a UML tool, not PlantUML.
- **Note on the shipped image**: SVG rasterised to PNG via `svglib`/`reportlab`, same as `visitor_pattern`, no content change.
- **Why chosen**: unambiguous, cleanly labelled (`<<use>>`, `<<create>>` stereotypes spelled out on the dependency lines), a good low-noise contrast case against the messier real diagrams above. Two inheritance, two dependency.

### `composite_pattern` (`composite_pattern.png`)
- **Source**: [File:Composite UML class diagram (fixed).svg](https://commons.wikimedia.org/wiki/File:Composite_UML_class_diagram_(fixed).svg), Wikimedia Commons.
- **Author**: Trashtoy, 2006; derivative by Aaron Rotenberg, 2010.
- **Licence**: Public domain, dedicated by the copyright holder.
- **Tool**: hand-coded in a text editor.
- **Why chosen**: a self-referential aggregation (`Composite` aggregates `0..*` `Component`, and a `Component` can itself be a `Composite`) — a structurally different aggregation shape than anything else in the holdout, with both role names (`parent`/`child`) and both multiplicities labelled on the same edge.

### `state_pattern` (`state_pattern.png`)
- **Source**: [File:State Design Pattern UML Class Diagram.svg](https://commons.wikimedia.org/wiki/File:State_Design_Pattern_UML_Class_Diagram.svg), Wikimedia Commons.
- **Author**: JoaoTrindade (original PNG, English Wikipedia); SVG conversion and edits by Ertwroc and FeRDNYC.
- **Licence**: Dual CC BY-SA 3.0 Unported and GNU Free Documentation License v1.2+.
- **Tool**: unspecified; format-converted from PNG, not PlantUML.
- **Why chosen**: a genuinely ambiguous notation case, kept rather than smoothed over — `ConcreteStateA`/`ConcreteStateB` connect to `State` via a dashed line with a hollow triangle (realization notation) even though `State`'s box shows no `<<interface>>` stereotype or italics. Recorded as `realization` to match the glyph actually drawn, per this project's own rubric guidance (T3.4) to trust the notation over inferred semantics.

## Self-generated (2 of 8)

### `media_library_icons` (`media_library_icons.png`)
- **Source**: authored for this holdout — IR at `corpus/holdout/ir/media_library_icons.json`, generated via the project's own `ir_to_puml`, with the `skinparam classAttributeIconSize 0` line stripped before rendering so PlantUML emits its true default icon-style visibility markers (colour-coded circles/squares) instead of the plain `+`/`-`/`#`/`~` text every other corpus and holdout image uses.
- **Licence**: ours; no restriction.
- **Covers**: inheritance (x2), composition, association, a static method, an abstract class with an abstract method — the two diagrams the icon requirement calls for are this one and the JPEG below.

### `order_processing_compressed` (`order_processing_compressed.jpg`)
- **Source**: authored for this holdout — IR at `corpus/holdout/ir/order_processing_compressed.json`, rendered normally then downscaled/upscaled and re-saved at JPEG quality 25 to simulate a low-quality phone screenshot.
- **Licence**: ours; no restriction.
- **Covers**: composition, directed association, dependency (x2), and genuine JPEG compression artefacts (blur/ringing around text and lines) — satisfies the "at least one screenshot with compression artifacts" requirement.

## Coverage check

All seven `RelKind` values appear at least once across the eight files: inheritance (`wikipedia_domain_model`, `media_library_icons`, `observer_pattern`, `factory_method_pattern`, `composite_pattern`), realization (`wikipedia_domain_model`, `visitor_pattern`, `state_pattern`), composition (`media_library_icons`, `order_processing_compressed`), aggregation (`wikipedia_domain_model`, `visitor_pattern`, `observer_pattern`, `composite_pattern`, `state_pattern`), association (`media_library_icons`), directed_association (`order_processing_compressed`), dependency (`wikipedia_domain_model`, `visitor_pattern`, `order_processing_compressed`, `factory_method_pattern`).

6 of 8 diagrams are real and publicly sourced (up from 2 of 4); the icon-marker and JPEG-compression requirements T3.26 established stay covered (`media_library_icons` for icons; `order_processing_compressed` and now `observer_pattern`, a genuine real-world JPEG, for compression).
