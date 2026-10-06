# Design files

Tilda style reference, exported from Refero (refero.design, "Tilda"). Source of truth for the web UI's look. Read `DESIGN.md` before any UI work.

| File | Role |
|---|---|
| `DESIGN.md` | Narrative rules: components, do/don't, surfaces. |
| `tokens.json` | DTCG token source of record. |
| `variables.css` | `:root` custom properties. |
| `theme.css` | Tailwind v4 `@theme` block. |

## Local changes to the export

- `variables.css`: `--section-gap`, `--card-padding`, `--element-gap` held ranges (`96-120px`), invalid CSS. Now single values: 96px, 32px, 16px.
- `variables.css`, `theme.css`: added `--font-mono` (system stack). The export defines no monospace family; the code pane needs one.
- `DESIGN.md` and `tokens.json` are unchanged.

## Decisions

- **Coral.** The export contradicts itself: the colour table and Agent Prompt Guide say coral must not be the primary CTA colour; Components and Do/Don't make the coral pill the primary CTA. This UI follows Components: the Regenerate button is the only coral element. To switch to the neutral reading, change the `cta` variant in `web/src/components/ui/button.tsx` to the dark variant.
- **Font.** TildaSans is Tilda's proprietary typeface; no licence to redistribute it was found. The UI ships Inter (the substitute `DESIGN.md` names), self-hosted through `@fontsource-variable/inter`. No runtime font CDN calls. `--font-tildasans` keeps its name, so a licensed TildaSans file could be dropped in later.
