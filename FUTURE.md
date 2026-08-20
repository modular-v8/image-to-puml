# Future work

Everything deliberately deferred, with why it was deferred and what would justify picking it up. Extracted from `tasks.md` on 2026-08-21 so the reasoning survives outside a 1,100-line task log.

Nothing here is a known defect. Defects that were found got fixed; these are decisions to stop, each with the evidence that made stopping reasonable at the time.

---

## Newly unblocked

**Re-test the icon-visibility prompt mapping (was T3.32).**
An explicit mapping from PlantUML's coloured attribute icons (green circle → `+`, red square → `-`, yellow diamond → `#`, blue triangle → `~`) to visibility markers was added, then reverted. The reason for reverting was procedural rather than evidential: its stated survival condition was vindication against a holdout diagram using icon markers, and the only such diagram — `media_library_icons` — never once produced a scoreable result across every configuration tried.

**That precondition no longer holds.** T4.22 found `media_library_icons` scores cleanly on a plain retry (5 classes), for the first time in the project's history. The experiment that was impossible to run is now runnable, and it is cheap: restore the prompt paragraph, score the holdout, keep or revert on the number. This is the single most actionable item on this page.

---

## Box detection

`perception/boxes.py` is retained but **not on the active pipeline path** — nothing calls it. It exists because the per-connector track (below) needed class bounding boxes, and it stays because it is tested (10 tests, `tests/unit/test_boxes.py`) and because the measurement that led to abandoning it is itself a finding.

T3.11 improved contour detection from 0/13 to 7/17 exact count matches and eliminated the "returns zero boxes" failure entirely, by sweeping candidate thresholds against a class count already known from stage A rather than trusting one fixed constant. It still did not pass its quality gate: visual inspection showed count-matching can mask a wrong answer (`visitor_pattern` matched coincidentally, not correctly). The gate was left unchecked rather than rounded into a pass.

Remaining failure modes, in decreasing order of likely payoff per effort:

1. **Touching shapes.** A vertical inheritance chain whose arrows meet box edges merges neighbouring boxes into a single contour. A morphological opening pass (erode, then dilate) before `findContours` would likely separate them without per-diagram tuning. Untried.
2. **Note-box confusion.** PlantUML notes render with a folded top-right corner, a genuinely different shape the current filter does not distinguish from a class box. Corner-fold detection, or an aspect-ratio and text-density heuristic, would exclude them specifically.
3. **Thin-sliver artifacts.** A low-area, extreme-aspect-ratio contour surviving between two adjacent boxes. The existing `_MIN_ASPECT_RATIO` / `_MAX_ASPECT_RATIO` bounds (0.15–8.0) may simply need tightening, or containment suppression needs to account for near-adjacency rather than literal overlap.
4. **Model grounding against a capable model.** The original finding — that the shipped model returns coordinates outside image bounds more often than not, and not marginally — was never retested against a model with real grounding ability. `google/gemini-3.1-pro-preview` is a proven-callable option, and a ~5-call test of the box-grounding prompt alone would settle it, independently of that model's own extraction problems.

---

## Closed tracks, with their re-open conditions

**Per-connector relationship extraction.** Cropping the region spanning each relationship's two endpoint classes and interrogating that connector in isolation. Scoped, partially built (boxes only), cut at the box quality gate. The accuracy problem it was designed to solve resolved by cheaper means — a prompt rubric fix, a `max_tokens` bug fix, and a serving-tier change — and holdout kind accuracy now clears its bar comfortably.
*Re-opens if:* holdout kind accuracy given a correct pair falls below its 80% completion bar on a future re-score.

**Round-trip verification loop.** Built complete, tested, instrumented — then measured to *reduce* accuracy on both evaluation sets (relationship F1 −4.5% corpus, −7.1% holdout). It ships present but disabled, behind `--verify`, so the negative result is reproducible rather than merely asserted. The root cause appears to be that a narrower second look is not a more trustworthy signal than the original extraction, including for elements the original was already unsure about.
*Untested hypothesis:* restrict re-query to elements that are **both** disputed by the diff **and** below the confidence threshold, rather than every disagreement. That would stop the loop overwriting first-pass answers that were already right. Cheap to try; the machinery exists.

**Montage batching.** Tiling several connector crops into one labelled image to conserve request quota. Never needed once evaluation moved to a paid model with no rate limit. *Re-opens only if* per-connector work returns and quota becomes binding again — and only if measured accuracy-neutral against one-crop-per-call.

**Folder batch mode.** `uml-regen run ./diagrams/ -o ./out/` with per-file isolation and a summary table. Cut as the first scope reduction, per the spec's own stated cut order. The evaluation harness already loops internally through `api.py`, so nothing depends on a user-facing folder mode. Straightforward to add.

**PlantUML `package` blocks.** No corpus or holdout diagram has ever produced a populated `packages` field, so this would ship as untested dead code. *Re-opens if* a real diagram needs it.

---

## Model and provider

**Auto-wire the fallback model.** `dots-studio/dots-3-note-preview:free` measured 3/3 reliable in the original preflight against the shipped default's 2/3, at the cost of far more verbose output. It is documented but not wired up — switching is a one-line change to `DEFAULT_MODEL_ID`. Automatic fallback on repeated failure was never implemented.

**The free tier is the shipped default and is unstable.** Evaluation moved to the paid tier of the same model after the free tier lost 2 of 5 characterization runs to outright rate-limit failure and swung 12.7 points on kind accuracy across the three that completed. Interactive use keeps the free default deliberately, so a first run costs a stranger nothing — but that means the shipped experience is the less reliable one. A cost-aware auto-escalation path (free first, paid on failure) was never built.

**Paid-tier noise was never characterized.** The noise floor was measured on the free tier (n=3 usable runs). The paid tier's own run-to-run variance rests on n=1, which is why several later results carry an explicit single-sample caveat. A proper N=5 paid characterization would let those results be stated without hedging.

---

## Evaluation

**The holdout is eight diagrams.** Small for the weight it carries — completion bars, the conditional track's closure, and the headline numbers all rest on it. Expanding it is pure labelling work: no model calls, no quota, fragmentable into short sessions.

**Synthetic member F1 sits exactly at its regression floor** (75.0% against a >75% bar) rather than above it. Named rather than rounded into a pass. Member extraction on the synthetic corpus is the one metric with no headroom above its own floor.

---

## Out of scope by design

These were excluded in the original spec and remain excluded. Listed so a reader knows they were considered, not overlooked.

- **Hand-drawn and whiteboard diagrams.** The open research frontier. Including it would have consumed the schedule and produced worse results on the case that actually mattered.
- **Diagram types other than class diagrams** — sequence, activity, state, component, use-case. Each has different syntax and a different perception problem. This felt like a small addition several times during the project. It is not.
- **Local / offline inference.** The goal was demonstrating the approach is viable on public diagrams; a local path adds a model download, hardware assumptions, and a second accuracy baseline. The `VisionClient` interface keeps it a drop-in addition — no provider-specific type leaks past it.
- **PDF, SVG, or multi-page input**, and multiple images composing one diagram.
- **Publishing to PyPI.** Installable from source meets the distribution goal without a release process.
- **Parsing arbitrary existing `.puml`.** The tool writes PlantUML; it does not read it. The evaluation corpus avoids needing a parser by being authored as IR first.
