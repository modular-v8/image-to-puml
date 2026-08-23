# uml-regenerator

Reproduce UML class diagrams from images into editable `.puml` source.

## What this project found

It was built on the research literature's premise that **relationship extraction is where vision models fail** on UML class diagrams, and that closing that gap needs specialised machinery. Measured on this pipeline, the premise did not hold — and the machinery did not help.

- **Relationship-kind discrimination was never the bottleneck.** Kind accuracy given a correct pair measured **91.7%** on the synthetic corpus and **76.0%** on the hand-labelled holdout (full-coverage figures, see below), against a pessimistic expectation of 50–65% — still comfortably clear of that floor, though the holdout figure specifically now sits below spec's 80% completion bar once every diagram is counted; see the diagnosis under [Baseline accuracy](#baseline-accuracy) for why.
- **The per-connector crop pass was scoped, partially built, and cut** at its quality gate — neither model-grounded bounding boxes nor OpenCV contour detection proved reliable enough to crop on. The gate caught it before the expensive half was written.
- **The render-and-compare verification loop was built completely, then measured worse than not running it** (relationship F1 −4.5% corpus, −7.1% holdout). A narrower second look at an element the model was already unsure about is not a more trustworthy signal than the first look. The code ships documented and disabled by default.
- **What actually moved the numbers was mundane**: one prompt rubric edit — an explicit rule against reading note-attachment lines as relationships — worth +7–8 points of relationship F1 and pair recall on *both* sets; a `max_tokens` bug fix; and switching the evaluation instrument from a free serving tier to a paid one.
- **The bug worth stealing.** With no completion cap, the model occasionally entered a degenerate repetition loop: one observed response ran 65,536 tokens and ~2 million characters, took ~18 minutes, and cost 40–50× the median call. It was the real cause of every multi-hour evaluation run on this project — misattributed to model speed until the raw cache entries were opened.
- **Closing the failure-rate gap changed the accuracy picture, not just the coverage picture.** A retry-once-then-fail policy on repetition events (built directly on the bug above) took the failure rate from 4/17 diagrams (24%) to 0/17 — every diagram now scores, including one that had never once produced a result before. Full coverage wasn't free: it exposed that a previously-unscored diagram scores badly on relationships, and most of that turned out to be one class name — `MediaItem` — misread as `Medialtem` by the model, then treated as a completely different, unmatched class by a scorer that matches names exactly on purpose. A scoring-methodology artifact amplifying a small perception slip, not a broad relationship-understanding regression — full diagnosis under [Baseline accuracy](#baseline-accuracy).
- **The holdout inverted the synthetic corpus's headline.** Nine hand-authored PlantUML renders overstated relationship-kind accuracy by ~17 points while *understating* member accuracy by ~15. Moving the holdout from a late buffer to the phase gate was the highest-value scheduling decision made here.

Figures, the A/B trail, and every superseded measurement are under [Baseline accuracy](#baseline-accuracy). **The ceiling experiment answered its own question directly: the residual gap is the pipeline, not the model.** Run unchanged through the same harness, a frontier model (`google/gemini-3.1-pro-preview`) scored *worse* than the shipped cheap model on the corpus (member F1 42.9% vs. 75.0%, relationship F1 77.1% vs. 95.2%) and failed to score outright on 41% of diagrams, against 12% for the shipped model — see [Baseline accuracy](#baseline-accuracy) for the full breakdown.

## Installation

### Prerequisites

The renderer shells out to `plantuml.jar`, which needs a JRE and Graphviz (`dot`) on `PATH`.

**Windows** (verified on Windows 10, via `winget`):

```powershell
winget install --id EclipseAdoptium.Temurin.21.JRE -e
winget install --id Graphviz.Graphviz -e
```

The Graphviz installer does not currently add itself to `PATH`; add it manually if `dot -V` fails after install:

```powershell
[System.Environment]::SetEnvironmentVariable(
  "Path",
  [System.Environment]::GetEnvironmentVariable("Path","User") + ";C:\Program Files\Graphviz\bin",
  "User"
)
```

Then fetch `plantuml.jar` (no installer; it's a standalone jar):

```bash
mkdir -p tools
curl -sL -o tools/plantuml.jar https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar
```

**Versions verified during development:**

| Tool | Version | Install method |
|---|---|---|
| JRE | Eclipse Temurin 21.0.12+8 (OpenJDK 21.0.12 LTS) | `winget install --id EclipseAdoptium.Temurin.21.JRE` |
| Graphviz | 16.0.0 | `winget install --id Graphviz.Graphviz` |
| PlantUML | 1.2026.6 | direct jar download (see above) |

Verify the toolchain:

```bash
java -jar tools/plantuml.jar -testdot
```

Expected output: `Installation seems OK. File generation OK`.

### Project setup

To develop on this repo, or run everything from within a clone:

```bash
uv python pin 3.12
uv sync
```

Commands below in this README assume this path — every `uml-regen ...` is `uv run uml-regen ...` from inside the clone.

### Installing as a standalone command

If you just want the `uml-regen` command available globally, without keeping a clone around:

```bash
uv tool install "git+https://github.com/modular-v8/image-to-puml.git"
```

(Once a tagged release exists, pin to it with `@v0.1.0` appended to the URL, e.g. `...image-to-puml.git@v0.1.0` — untagged installs above track `main`.)

This installs a real `uml-regen` executable — no `uv run` prefix needed. One thing changes: `plantuml.jar`'s default location (`tools/plantuml.jar`) is resolved relative to your *current directory*, which only makes sense inside a clone. Running as a standalone tool from an arbitrary directory, point `UMLREGEN_PLANTUML_JAR` at wherever you downloaded it instead:

```bash
export UMLREGEN_PLANTUML_JAR=/absolute/path/to/plantuml.jar
uml-regen doctor
```

### API key

Get a key from [openrouter.ai/keys](https://openrouter.ai/keys) (the free tier needs no payment method). The CLI reads `OPENROUTER_API_KEY` from the environment; a `.env` file in the project root is also picked up automatically (real environment variables always win over it). **Never commit `.env`** — it's already covered by `.gitignore`.

```bash
echo 'OPENROUTER_API_KEY=your-key-here' > .env
```

### Verify the install

```bash
uv run uml-regen doctor
```

Reports the JRE, Graphviz, `plantuml.jar`, and API key presence (never the key's value), plus the resolved cache location. Exits non-zero and names the specific missing piece if anything's wrong.

## Usage

```bash
uv run uml-regen run path/to/diagram.png
```

Produces `diagram.puml` (the deliverable) and `diagram.review.md` (any relationships below the confidence threshold, each with its `.puml` line number) next to the input image. Nothing is rendered to an image unless you ask for it:

```bash
uv run uml-regen run path/to/diagram.png --render svg
```

Common flags (`uv run uml-regen run --help` for the full list):

| Flag | Effect |
|---|---|
| `-o / --output PATH` | Where to write the `.puml` file. Defaults to the input image's path with a `.puml` extension. |
| `--render svg\|png\|pdf` | Also render the `.puml` to this format. Omit for `.puml` only. |
| `--model MODEL_ID` | Override the configured vision model (see [Model selection](#model-selection-openrouter-free-tier) below). |
| `--no-cache` | Bypass the response cache entirely (no read, no write). |
| `--verify / --no-verify` | Round-trip verification pass. **Off by default** — measured to make relationship F1 *worse*, not better (see [What this project found](#what-this-project-found)). Ships present so that negative result is reproducible. |
| `-v`, `-vv` | Increase output detail (model/class/relationship counts, then cost/latency/verify stats). |

Two other commands exist for reproducing this project's own evaluation runs rather than everyday use — `uv run uml-regen corpus` (regenerate the fixture corpus from `corpus/ir/*.json`) and `uv run uml-regen eval` (score extraction against a labelled IR directory); `--help` on each documents their flags.

## Model selection (OpenRouter free tier)

T2.6's preflight investigation: which free vision-capable models on OpenRouter actually accept an image and return reliably parseable JSON. Candidates were queried live from OpenRouter's `/models` endpoint (hardcoded guesses 404'd -- the free catalog changes), then each was sent the same real diagram ([`corpus/img/ecommerce_checkout.png`](corpus/img/ecommerce_checkout.png), 8 classes) with a prompt asking for class count and names as JSON, multiple times per model to check consistency rather than trusting a single sample.

| Model | Image support | JSON reliability | Notes |
|---|---|---|---|
| `google/gemma-4-31b-it:free` | Untested | N/A | 429 rate-limited on all 3 attempts across two test rounds -- too congested on the free tier to use reliably |
| **`google/gemma-4-26b-a4b-it:free`** (chosen default) | Yes | 2/3 correct, 2/3 valid JSON | Cheap and fast when it works (47-290 completion tokens); failed once by hallucinating a 9th class, failed once more with malformed/truncated JSON output |
| `nvidia/nemotron-nano-12b-v2-vl:free` | Nominally yes | N/A -- unusable | Returns HTTP 200 with an embedded `{"error": {"code": 504, "message": "Upstream idle timeout exceeded"}}` body instead of an HTTP error status, both times tested. `openrouter.py` now detects this shape and raises a clear error rather than crashing on a missing `choices` key |
| `dots-studio/dots-3-note-preview:free` (documented fallback) | Yes | 3/3 correct, 3/3 valid JSON | Perfectly reliable across every sample so far, but far more verbose (1000+ completion tokens vs. Gemma's ~100) -- still $0 on the free tier, just slower |

**Chosen default: `google/gemma-4-26b-a4b-it:free`**, on cost/speed grounds, accepting its ~2/3 reliability for now -- the schema-validation repair-retry (T2.12) and the `--verify` round-trip loop (Phase 3) are the system's designed answers to exactly this kind of occasional bad response, so a model that's fast-but-imperfect is a reasonable bet as long as those safety nets exist. `dots-studio/dots-3-note-preview:free` is the documented fallback if Gemma's failure rate turns out to matter in practice; switching is a one-line change to `DEFAULT_MODEL_ID` in `config.py` (or `UMLREGEN_MODEL_ID`) -- no automatic fallback is wired up. This default is for **interactive use only**, kept free-tier deliberately so a stranger's first run costs $0 -- see below for what evaluation runs use instead.

### Evaluation model (T3.35/T3.36, 2026-08-18)

T3.35 characterized the free tier's actual reliability under sustained load, not just single-sample spot checks: running the corpus five times in a row, cache disabled, identical prompts and config. Two of the five runs failed outright -- every diagram 429'd after retries -- and one successful run took 77 minutes against another's 10.5, degrading before the eventual collapse. The three runs that did complete swung **12.7 points on kind accuracy given a correct pair** (76.9%-89.6%) with literally nothing changed between them. That figure matters beyond this one measurement: it set the noise floor every scored comparison in this project is now checked against (tasks.md, Day 9b) -- a delta smaller than a metric's own run-to-run range isn't evidence of anything.

Against that, a single completed run on **`google/gemma-4-26b-a4b-it`** (the same model's paid tier, chosen specifically to isolate free-vs-paid serving rather than introduce a second variable) beat every free-tier run's range on class recall and kind accuracy, with zero short/incomplete responses, at a cost of roughly $0.07 per million tokens -- negligible.

**Decision: evaluation and scored-comparison work uses the paid tier from here on**; `DEFAULT_EVAL_MODEL_ID` in `config.py` (`UMLREGEN_EVAL_MODEL_ID` to override) is `google/gemma-4-26b-a4b-it`, distinct from `DEFAULT_MODEL_ID`'s free-tier interactive default. Every scorecard in this README and `tasks.md` from T3.35 onward is on the paid tier unless stated otherwise; earlier figures (T2.21's baseline, T3.27's holdout gap) were measured on the free tier and are labelled as such where they appear.

### The multi-hour eval runs, explained (T3.37, 2026-08-18)

T3.35 and T3.37's early attempts both took far longer than expected -- one run over an hour for a single 9-diagram pass. Root cause: `openrouter.py` sent every request with **no cap on output length**. This model occasionally enters a degenerate repetition loop (garbage tokens, not real content) and, uncapped, ran until hitting the provider's own ceiling -- observed once at 65,536 completion tokens and a 2-million-character response, versus every legitimate response this project has ever recorded being under ~1000 tokens. At the model's observed throughput that alone is roughly 18 minutes for one bad call. **Fixed**: every request now caps `max_tokens` at 4096. This is not a "production is slow" problem -- a normal interactive run (two calls, a few hundred tokens each) takes seconds; it was specifically unbounded worst-case generation, now bounded.

## Baseline accuracy

### Current reference (T5.4 — full coverage, retry-once-on-repetition policy active)

Measured 2026-08-20 on `google/gemma-4-26b-a4b-it` (paid), $0.0135 total, via `scripts/run_baseline.py` / `scripts/run_holdout.py` unmodified. **Every diagram in both sets now scores** — the failure rate that sat at 4/17 (24%) since T4.22 dropped to 0/17 once a `RepetitionDetected` response gets one fresh, unmodified retry (T5.3) instead of failing immediately. That includes `media_library_icons`, which had never once produced a scoreable result before this run.

| Metric | Corpus (9 diagrams) | Holdout (8 diagrams) |
|---|---|---|
| **Failure rate** | **0/9 (0%)** | **0/8 (0%)** |
| Class recall | 100.0% | 95.0% |
| Class precision | 100.0% | 97.5% |
| Member F1 | 66.7% | 98.9% |
| Relationship F1 | 81.2% | 72.7% |
| Pair recall | 87.3% | 87.5% |
| Kind accuracy (given a correct pair) | 91.7% | 76.0% |
| Cost | $0.0074 | $0.0061 |

**Closing the coverage gap wasn't free — it's the more honest number, but a worse-looking one on relationships.** Against the T3.42 partial-coverage reference below, corpus member F1 (75.0%→66.7%) and pair recall (98.2%→87.3%) now fall below their synthetic regression floors, and holdout pair recall (96.4%→87.5%) and kind accuracy (84.9%→76.0%) now fall below their completion bars; holdout class recall (97.1%→95.0%) lands exactly on its bar rather than above it.

**The holdout drop was investigated directly — two diagrams, two different and specific causes, traced by replaying both against the same cache and inspecting the model's own per-relationship evidence strings (`scripts/diagnose_t54_regressions.py`), not inferred from the score alone:**

- **`media_library_icons`'s pair-recall damage is a scorer artifact amplifying a one-character misread, not a relationship failure.** The class `MediaItem` — rendered in italics, PlantUML's convention for an abstract class — was read back by the model as `Medialtem`: capital `I` and lowercase `l` are close to indistinguishable in that rendering. The scorer matches class names exactly by design (fuzzy matching would hide real errors), so all three relationships touching `MediaItem` score as *both* hallucinated (wrong-named target) and missed (right-named target absent), even though the model identified the right two classes and roughly the right relationship each time. This is what mainly drives the holdout **pair recall** drop.
- **`observer_pattern` and `media_library_icons` both drag down holdout kind accuracy, for different reasons, weighted equally by this project's macro-averaging** (mean of per-diagram scores, established at T2.19 — one diagram's kind-accuracy figure counts the same regardless of how many relationships fed it). `observer_pattern` is a genuine, confirmed model error: its two `ConcreteObserver→Observer` edges are solid lines with hollow triangles in the source image — standard UML inheritance notation — but the model's own evidence text claims "dashed line" (the diagram's only actual dashed line is an unrelated note attachment elsewhere) and classifies both as `realization` instead of `inheritance`, apparently keying off the triangle shape without correctly reading line style. That gives the diagram a 33% kind-accuracy score (1 of 3 correct). `media_library_icons` contributes here too, separately from the pair-recall issue above: its one correctly-paired relationship (`Book→Publisher`) was also called the wrong kind (`directed_association` instead of `association`), giving it a 0% kind-accuracy score from a single data point — which counts exactly as much toward the average as `observer_pattern`'s three.

Both diagrams also carry smaller, already-known-hard confusions riding along (composition-vs-aggregation on a filled/hollow diamond, flagged as hard since T3.4/T3.32; inheritance-vs-directed_association on a couple of triangle arrowheads) that are not newly discovered.

**The corpus-side drop (member F1, pair recall) has not been diagnosed the same way** — it involves different diagrams (`library_system` at 33% pair recall and `animal_kingdom` at 67% are the worst corpus offenders) that this investigation didn't dig into, so no specific cause is claimed for it here. Read the holdout diagnosis above as explaining the holdout numbers specifically, not as a general explanation for every regression on this page. T3.35's noise band on kind accuracy (~±13%) still applies on top of all of this and hasn't been re-measured against the new configuration.

### Pre-retry-policy reference (T3.42) — superseded by the figures above, kept for the A/B trail

Measured 2026-08-19 on `google/gemma-4-26b-a4b-it` (paid), $0.0233 total, before T5.3's repetition retry policy existed. Two diagrams (`shape_hierarchy`, `media_library_icons`) failed to score at all and were excluded from these averages — which is exactly why the figures below look better than the full-coverage numbers above on relationship metrics specifically.

| Metric | Corpus (8/9 diagrams) | Holdout (7/8 diagrams) |
|---|---|---|
| Class recall | 100.0% | 97.1% |
| Member F1 | 75.0% | 100.0% |
| Relationship F1 | 95.2% | 82.0% |
| Pair recall | 98.2% | 96.4% |
| Kind accuracy (given a correct pair) | 95.8% | 84.9% |

At the time, against spec's holdout completion bars, all four passed (class recall 97.1% >95%, member F1 100.0% >85%, pair recall 96.4% >90%, kind accuracy 84.9% >80%, the last one thin against T3.35's ±13% noise band) — which is why the conditional track (bounding boxes + per-connector pass, see below) stayed closed. That conclusion about the conditional track still stands; the underlying accuracy figures do not, now that coverage is complete.

### Phase 3 close-out: two built-and-measured negative results

- **The conditional track** (model-grounded bounding boxes and a per-connector relationship pass) was scoped, partially built, and closed at its own quality gate before the expensive half was written — neither model-grounded boxes nor OpenCV contour detection proved reliable enough to crop on. It reopens automatically if a future re-score drops holdout kind accuracy below 80%. **That condition is technically met by T5.4's 76.0% figure above** — flagged here rather than acted on silently. The diagnosis above attributes most of that number to two specific causes (a scorer artifact on one diagram, a genuine but small 2-relationship confusion on another) on a set of only 8 diagrams under macro-averaging, which is a thin basis for reopening a track that was previously closed on stronger evidence; treat this as an open decision for the project owner, not a conclusion this page draws on its own.
- **The render-and-compare verification loop** was built completely, tested offline (103/103), instrumented for cost/latency, and measured against both sets — and it measurably *hurts* accuracy (relationship F1 −4.5% corpus / −7.1% holdout; kind accuracy −7.1% holdout), even after fixing two real bugs the measurement itself uncovered. It ships disabled by default.

### Ceiling experiment (T3.28) — `google/gemini-3.1-pro-preview`, 2026-08-19

The question this experiment exists to answer: is the residual gap between measured accuracy and 100% a limit of the *model* or of the *pipeline*? Run through the exact same harness as every other figure on this page — no prompt edits, no schema changes, only the model ID (plus a narrowly-scoped, user-confirmed follow-up: two diagrams whose stage-B response was confirmed truncated at the harness's `max_tokens=4096` cap were retried with the cap raised to 12,000, after clearing their stale cached responses). Total cost across both passes: ~$1.3. Full diagnostic account, including three distinct failure modes found in the raw responses, is at `tasks.md` T3.28.

| Metric | Corpus (7/9 scored) | Holdout (3/8 scored) |
|---|---|---|
| Class recall | 100.0% | 100.0% |
| Member F1 | 42.9% | 97.2% |
| Relationship F1 | 77.1% | 88.9% |
| Pair recall | 76.2% | 90.5% |
| Kind accuracy (given a correct pair) | 85.7% | 93.3% |

**The answer is unambiguously the pipeline, not the model.** Compared against the shipped configuration's current (T5.4, full-coverage) figures above, the frontier model scores *worse* on every corpus metric except class recall (member F1 42.9% vs. 66.7%; relationship F1 77.1% vs. 81.2%; pair recall 76.2% vs. 87.3%), and **7 of 17 diagrams (41%) failed to score outright**, against 0 of 17 (0%) for the shipped cheap model on the same two sets under T5.4's retry policy — the gap was already stark at the original 12% comparison point and is more so now. This comparison predates T5.3's repetition retry policy; the ceiling model's own 41% failure rate has not been re-measured with a retry policy applied and may well also improve with one, so read the failure-rate gap specifically as directional, not a controlled A/B. The failures split into three kinds: genuine truncation at a token cap tuned for a different, more compact model (fixed by retrying at a higher cap); a degenerate repetition loop identical to a pathology T3.37 already found and capped against, recurring on this different model; and outright decline — six diagrams where the model returned complete, valid JSON with zero classes and an explanatory warning, nowhere near the token cap, on diagrams the cheap shipped model handles without issue. A more capable underlying model, run through this project's exact two-stage extraction with its loosely-enforced JSON schema, does not perform better here — it fails more often, and when it succeeds it frequently omits members it clearly had headroom to report. Because this is a `-preview` model, treat this figure as a point-in-time measurement, not something reproducible on demand.

### Pre-Phase-3 reference point (T3.37) — superseded by the figures above, kept for the A/B trail

Measured 2026-08-18 on `google/gemma-4-26b-a4b-it` (paid), with prompts at their pre-Phase-3 state, one run per set, total cost $0.02. This is what T3.38/T3.39's A/B comparisons were measured against.

| Metric | Corpus (9 diagrams) | Holdout (8 diagrams) |
|---|---|---|
| Class recall | 100.0% | 95.0% |
| Member F1 | 66.7% | 100.0% |
| Relationship F1 | 86.9% | 80.1% |
| Pair recall | 90.1% | 87.5% |
| Kind accuracy (given a correct pair) | 94.4% | 82.6% |
| Cost | $0.0076 | $0.0124 |

### Original baseline (Phase 2, T2.21) — free tier, superseded as a comparison point but kept for the record

The "before" figures, measured 2026-08-17 against the full 9-diagram corpus (`corpus/ir/*.json` as ground truth, `corpus/img/*.png` as input), using the default model. Entirely a synthetic, hand-authored corpus -- **no hand-labelled holdout exists yet** (moved to the Day 12 buffer per tasks.md), so read these with the synthetic-corpus-overfitting risk spec.md already names, not as a final result. Full per-diagram breakdown and future runs accumulate in `runs/run_log.jsonl` (local, gitignored).

| Metric | Baseline |
|---|---|
| Class recall | 100.0% |
| Class precision | 100.0% |
| Class F1 | 100.0% |
| Member F1 | 77.8% |
| Relationship F1 | 87.3% |
| Pair recall | 98.4% |
| Kind accuracy (given a correct pair) | 88.0% |
| Total cost (9 diagrams) | $0.00 |
| Warnings | 0 |

The one original target this baseline didn't clear was Member F1 (77.8% vs. an original 85% target) -- notably, **not** relationship-kind discrimination, which spec.md calls out as the central hard problem and where this baseline (88.0% kind accuracy given a correct pair) came in well above the original pessimistic 50-65% expectation. spec.md's provisional accuracy targets have been revised against this baseline -- see spec.md §acceptance criteria for the full before/after with rationale per metric.

## Limitations

- **Hand-drawn or whiteboard diagrams are out of scope.** Everything measured on this page is a rendered or photographed *digital* diagram. Reading a photo of a whiteboard sketch is a different, harder perception problem that was deliberately not attempted here — noted as future work, not a gap that's expected to close on its own.
- **Class diagrams only — and UML *object*/instance diagrams (`instanceName : ClassName` labels) are a different notation the tool will silently mishandle, not reject.** Sequence, activity, state, component, use-case, and object diagrams each use different notation and pose a different perception problem; none are supported. A real first-use test (T5.12) confirmed this concretely: fed a diagram using instance-style labels, the tool kept only the instance name and silently dropped the class name after the colon for every box, with no warning that the input wasn't the notation it expects.
- **Correctness is only claimed up to 15 classes and 25 relationships.** Beyond that bound the tool still runs and emits a warning rather than refusing, but it's best-effort, not a guarantee — in one internal robustness test at exactly 15 source classes, the model hallucinated a 16th and tripped the bounds warning on an image that wasn't actually oversized.
- **No folder/batch mode — one image per invocation.** Scoped and then cut (T4.5, 2026-08-20) per spec's own stated cut-order when the schedule needed slack; the eval harness still loops internally, but there's no user-facing way to process a directory of images in one command.
- **`--verify` ships disabled by default.** It was built, measured, and found to make relationship F1 *worse*, not better, on both evaluation sets (see [What this project found](#what-this-project-found)). It's present so that negative result is reproducible, not because turning it on is recommended.
- **`review.md`'s confidence score is not a real correctness signal.** It's one of two hardcoded placeholder values, not something the model is actually asked for (T4.16) — the two sources meant to eventually replace it with a real signal (per-connector cropping, verification-loop agreement) were respectively cut and shipped disabled. Confirmed again in real use at T5.12: a diagram where every relationship had a kind or topology error had zero relationships flagged. Treat `review.md` as a mechanically-correct sidecar (its line numbers are right when it does flag something), not as a reliable guide to what to check by hand.
- **The accuracy scorer matches names exactly, by design, not fuzzily.** This is a deliberate strictness choice (see `ir/diff.py`), but it means a single misread character in a class name — as happened with `MediaItem`/`Medialtem` above — can look like a large relationship-accuracy failure in the metrics when the actual perception error was much smaller. Read any single low score in isolation with that in mind.
- **Cloud-only inference.** Every image is sent to OpenRouter. There's no local/offline mode, so this tool isn't suitable for confidential or employer-owned diagrams — free-tier providers may retain inputs for product improvement, and even paid tiers are a third party you're trusting with the image.
- **Single image in, `.puml` text out.** No PDF, SVG, or multi-page input; no combining multiple images into one diagram; and the tool doesn't parse or round-trip arbitrary existing `.puml` — it only generates from an image.
- **CLI and library only.** No GUI, no web interface, and no PyPI package — install from source via `uv`, as shown above.
- **Several spec.md acceptance bars are currently unmet, by design or by measurement — none silently dropped.** Two accuracy floors/bars specifically (corpus pair recall, and three of four holdout completion bars) fell below their line when T5.4 closed the failure-rate gap to 0% — diagnosed above, not glossed over. Two functional criteria are unmet outright: `--verify` beating no-verify (a measured negative result) and the batch-mode test (the feature was cut). spec.md's own acceptance-criteria section carries the full item-by-item resolution, dated 2026-08-23.
