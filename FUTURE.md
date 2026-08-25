# Future work

Ideas deliberately left for later, with why they were set aside and what would justify picking each one up.

Nothing here is a known bug. Bugs that were found got fixed; these are places where the team chose to stop, each with the reasoning that made stopping reasonable.

---

## Most actionable: re-test the icon-visibility mapping

PlantUML can render class-member visibility as coloured icons instead of `+`/`-`/`#`/`~` text markers (green circle → public, red square → private, yellow diamond → protected, blue triangle → package). An explicit mapping from those icons to visibility markers was built, then reverted — not because it measured badly, but because the one real-world diagram meant to validate it never produced a usable result at the time, for unrelated reasons (a model repetition glitch on that specific image).

That blocker has since cleared — a later retry produced a clean result on that same diagram. The experiment that was previously impossible to run is now cheap: restore the mapping, re-score the holdout set, and keep or revert based on the number. This is the single most actionable item on this page.

---

## Box detection (built, not used)

A module for locating class bounding boxes in an image — via the model's own coordinate grounding, with an OpenCV contour-detection fallback — is written and tested but not called anywhere in the active pipeline. It exists because a planned "crop each relationship's connector and interrogate it in isolation" feature needed reliable boxes first, and it's kept rather than deleted because the measurement that led to shelving it is itself useful evidence, and the code might be worth reviving later.

The contour-detection fallback got meaningfully better in its one improvement pass (roughly doubling its exact-match rate, and eliminating a "returns nothing" failure mode entirely) but still didn't clear the bar for trustworthy cropping — visual inspection showed it can get the right *count* of boxes while getting their actual locations wrong, which is worse than obviously failing.

Remaining failure modes, roughly in order of likely payoff per effort:

1. **Touching shapes.** A vertical inheritance chain whose arrows meet box edges merges neighbouring boxes into one detected blob. A standard image-processing technique (erode-then-dilate before contour detection) would likely separate them without diagram-specific tuning. Untried.
2. **Note-box confusion.** PlantUML's explanatory note boxes render with a distinctive folded corner that the current detector doesn't distinguish from a class box. Detecting that shape specifically, or filtering by text density, would exclude them.
3. **Thin sliver artifacts.** Small, oddly-shaped leftover contours between two adjacent real boxes. Likely fixable by tightening the existing size/shape filters or handling near-adjacent boxes more carefully.
4. **Testing box-grounding against a more capable model.** The finding that the shipped model's coordinate grounding is unreliable was never re-tested against a model known to be good at spatial grounding. A handful of calls against a stronger model would settle whether this is a shipped-model limitation or a harder problem.

---

## Closed tracks, with their re-open conditions

**Per-connector relationship extraction.** The idea: crop the image region spanning each relationship's two endpoint classes and ask about that connector in isolation, rather than the whole relationship list at once. Scoped and partially built (it depended on the box detection above), but shelved once it became clear relationship accuracy was already solid enough without it — the plain "ask about the whole diagram" approach turned out to work about as well.
*Worth revisiting if:* relationship-kind accuracy on real-world diagrams drops meaningfully below where it currently sits.

**Round-trip self-verification.** The idea: render the generated diagram back to an image, re-extract it, and compare the two — using disagreements as a signal to re-ask about specific relationships. Built completely and measured to make results *worse*, not better. It ships in the code, off by default, specifically so that result stays reproducible rather than becoming an unverifiable claim. The likely mechanism: a second, narrower look at something the model was already unsure about isn't a more trustworthy signal than the first look — it's just a second chance to be confidently wrong differently.
*Untried refinement:* only re-query elements that are both disputed by the comparison *and* already low-confidence, instead of every disagreement — that would stop the loop from overwriting first-pass answers that were already correct. Cheap to try; the machinery already exists.

**Batching multiple crops into one image.** A cost-saving idea for the per-connector approach above (tile several crops into one labelled request instead of one request per connector). Never needed once evaluation moved to a paid tier with no rate limit making the cost difference matter. Only relevant again if per-connector extraction comes back *and* request volume becomes a real constraint.

**Folder/batch mode.** Processing a whole directory of images in one command. Cut early to protect schedule, not because it's hard — the internal evaluation tooling already loops over many images, so exposing that as a user-facing folder mode would be a straightforward addition.

**PlantUML `package` blocks.** Nested package/namespace grouping in the output. No test diagram has ever needed it, so it was never built — would ship as untested code with no way to verify it works. Worth adding if a real diagram needs it.

---

## Make the confidence signal real

**The highest-priority item on this page.** The tool is meant to flag relationships it's unsure about in `review.md`, so a user knows what to double-check. As shipped, that flag doesn't actually work — the "confidence" value behind it is a hardcoded placeholder, not something the model is actually asked to assess. This isn't a case of the signal being weak or noisy; there currently isn't one. A real test found a diagram where every single relationship was wrong and not one was flagged.

Two paths could supply a real signal, and neither is currently wired up:
- **Per-connector cropping** (see Box detection, above) — if bounding boxes ever become reliable enough, asking about each relationship in isolation and using the model's own certainty there is a natural confidence source.
- **Self-verification agreement** (see Closed tracks, above) — using *whether the re-extraction agreed*, without ever letting it overwrite the original answer, is a different and untried use of that same machinery from the one that was already tried and shelved.

Of everything on this page, this is the one place where the documentation's own claim about what the tool does and what it actually does don't match — worth prioritizing above the rest of this list for that reason.

---

## The notation boundary: object/instance diagrams

Every diagram used to build and measure this tool used standard UML class-diagram notation. A real test on a diagram that instead used *object/instance* notation — where each box labels a specific instance of a class (`someObject : SomeClass`) rather than the class itself — found the tool doesn't fail gracefully on that input. It silently reinterprets the instance name as if it were the class name, drops the type information after the colon, loses every attribute, and loses every relationship's kind.

**A second test bounds this rather than leaving it an open mystery.** A follow-up on a genuine, uncurated class diagram — no instance labels — came back close to the tool's normal measured accuracy on every one of those same axes: attributes and methods came through essentially complete, relationships were correctly typed. The likely explanation: the unusual notation confused the *entire* extraction, not just the class-naming step specifically — this looks like a scope boundary the tool doesn't detect, not a general weakness on real-world diagrams.

What would justify picking this up: teaching the extraction to recognize object/instance notation as a distinct case — or, as a smaller first step, simply detecting it and warning rather than silently misreading it — is real, substantial perception-engineering work, not a quick fix, which is why it wasn't attempted immediately.

---

## Model and provider

**The default (free) model can rate-limit on a brand-new user's very first command.** A first-time run with no configuration hit this directly — the exact zero-setup path that's supposed to cost a stranger nothing. The error message now names the paid-tier override as a next step, so it's no longer a dead end, but the default path itself can still fail under load before a user learns to route around it. A smarter default — try free, automatically fall back to paid on repeated failure — was never built; this is the concrete case that makes it worth doing.

**A more reliable free-tier fallback model exists but isn't wired up.** One alternative model measured perfectly reliable in early testing, against the shipped default's roughly two-out-of-three reliability — at the cost of much more verbose (slower) responses. Switching the default is a one-line config change; automatic fallback on repeated failure from the primary model was never implemented.

**The free tier is measurably less reliable than the paid tier of the same model**, which is why all of this project's own accuracy measurements use the paid tier — a free-tier characterization run lost two out of five attempts to outright rate-limiting and swung double digits in accuracy across the runs that did complete, with nothing else changed between them. The free tier stays the interactive default anyway, deliberately, so a first run is free — which means the default experience is also the less reliable one.

**Paid-tier run-to-run variance was never properly characterized** — the same kind of measurement that revealed the free tier's instability was only ever done thoroughly on the free tier. A handful of repeated paid-tier runs would let later results be stated without an unverified assumption that the paid tier is stable.

---

## Evaluation

**The real-world holdout set is only eight diagrams.** Small for how much weight it carries — every headline accuracy number rests on it. Growing it is pure labelling work with no model calls and no cost, and can be done in small increments.

**One accuracy metric sits exactly on its own regression floor** rather than comfortably above it (member extraction accuracy on the synthetic test set). Worth watching — it's the one metric with no safety margin.

---

## Out of scope by design

Excluded deliberately from the start, and still excluded. Listed so a reader knows these were considered, not overlooked.

- **Hand-drawn and whiteboard diagrams.** The genuinely hard, open version of this problem. Attempting it would have consumed the project and produced a worse result on the case that actually mattered most.
- **Diagram types other than class diagrams** — sequence, activity, state, component, use-case. Each uses different notation and poses a different perception problem. This looked like it should be a small addition more than once during development. It would not have been.
- **Local or offline inference.** The goal was proving the approach works at all, on diagrams with no confidentiality requirement — a local model path would add a model download, hardware assumptions, and a second accuracy baseline to maintain. The architecture keeps this a clean addition later if it's ever needed: nothing provider-specific leaks past the internal interface that talks to the model.
- **PDF, SVG, or multi-page input**, and combining multiple images into one diagram.
- **Publishing to a package index.** Installing directly from the source repository meets the goal without needing an ongoing release process.
- **Reading or editing existing `.puml` files.** The tool only writes PlantUML; it doesn't parse it back in.
