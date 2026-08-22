# uml-regenerator

Reproduce UML class diagrams from images into editable `.puml` source.

## What this project found

It was built on the research literature's premise that **relationship extraction is where vision models fail** on UML class diagrams, and that closing that gap needs specialised machinery. Measured on this pipeline, the premise did not hold — and the machinery did not help.

- **Relationship-kind discrimination was never the bottleneck.** Kind accuracy given a correct pair measured **95.8%** on the synthetic corpus and **84.9%** on the hand-labelled holdout, against a pessimistic expectation of 50–65%.
- **The per-connector crop pass was scoped, partially built, and cut** at its quality gate — neither model-grounded bounding boxes nor OpenCV contour detection proved reliable enough to crop on. The gate caught it before the expensive half was written.
- **The render-and-compare verification loop was built completely, then measured worse than not running it** (relationship F1 −4.5% corpus, −7.1% holdout). A narrower second look at an element the model was already unsure about is not a more trustworthy signal than the first look. The code ships documented and disabled by default.
- **What actually moved the numbers was mundane**: one prompt rubric edit — an explicit rule against reading note-attachment lines as relationships — worth +7–8 points of relationship F1 and pair recall on *both* sets; a `max_tokens` bug fix; and switching the evaluation instrument from a free serving tier to a paid one.
- **The bug worth stealing.** With no completion cap, the model occasionally entered a degenerate repetition loop: one observed response ran 65,536 tokens and ~2 million characters, took ~18 minutes, and cost 40–50× the median call. It was the real cause of every multi-hour evaluation run on this project — misattributed to model speed until the raw cache entries were opened.
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

```bash
uv python pin 3.12
uv sync
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

### Current reference (Phase 3, T3.42 — the shipped configuration: T3.4 + T3.31 kept, T3.32 reverted)

Measured 2026-08-19 on `google/gemma-4-26b-a4b-it` (paid), $0.0233 total. This is what Phase 3 is judged on; T3.37's figures (below) were the pre-Phase-3 reference point for the A/B work, not the final answer, and T3.38/T3.39's own scorecards are superseded by this one since they briefly included T3.32, which was reverted after being measured.

| Metric | Corpus (8/9 diagrams) | Holdout (7/8 diagrams) |
|---|---|---|
| Class recall | 100.0% | 97.1% |
| Member F1 | 75.0% | 100.0% |
| Relationship F1 | 95.2% | 82.0% |
| Pair recall | 98.2% | 96.4% |
| Kind accuracy (given a correct pair) | 95.8% | 84.9% |

One diagram failed to score in each set (`shape_hierarchy`, `media_library_icons`) — both on genuinely unparseable model output, not the evidence-check issue T3.41 fixed. `media_library_icons` is the one holdout diagram built to test T3.32's icon-visibility mapping; it has never produced a scoreable result, which is why T3.32 stays reverted rather than reconsidered.

Against spec's holdout completion bars: class recall 97.1% (>95%, +2.1% margin), member F1 100.0% (>85%, +15.0%), pair recall 96.4% (>90%, +6.4%), kind accuracy 84.9% (>80%, **+4.9%**) — all four pass, which is why the conditional track (bounding boxes + per-connector pass, see below) stays closed. The kind-accuracy margin is real but thin: T3.35's noise band for that metric was roughly ±13%, wider than this margin, so treat "kind accuracy clears 80%" as currently true but not yet a settled fact.

Against the synthetic regression floors, the one that isn't cleanly met: member F1 floors at ">75%" and measured exactly 75.0%, not above it — a floor, not a completion bar, so this doesn't block anything, but it's named rather than rounded into a pass.

Two diagrams still fail to score under the shipped configuration: `shape_hierarchy` (corpus) and `media_library_icons` (holdout), both on genuinely unparseable model output on both the original attempt and the repair-retry. `media_library_icons` is the one holdout diagram built specifically to test the reverted icon-visibility prompt addition (T3.32) and has never produced a scoreable result across this entire phase.

### Phase 3 close-out: two built-and-measured negative results

- **The conditional track** (model-grounded bounding boxes and a per-connector relationship pass) was scoped, partially built, and closed at its own quality gate before the expensive half was written — neither model-grounded boxes nor OpenCV contour detection proved reliable enough to crop on. It reopens automatically if a future re-score drops holdout kind accuracy below 80%.
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

**The answer is unambiguously the pipeline, not the model.** Compared against the shipped configuration above, the frontier model scores *worse* on every corpus metric except class recall (member F1 42.9% vs. 75.0%; relationship F1 77.1% vs. 95.2%; pair recall 76.2% vs. 98.2%), and **7 of 17 diagrams (41%) failed to score outright**, against 2 of 17 (12%) for the shipped cheap model on the same two sets. The failures split into three kinds: genuine truncation at a token cap tuned for a different, more compact model (fixed by retrying at a higher cap); a degenerate repetition loop identical to a pathology T3.37 already found and capped against, recurring on this different model; and outright decline — six diagrams where the model returned complete, valid JSON with zero classes and an explanatory warning, nowhere near the token cap, on diagrams the cheap shipped model handles without issue. A more capable underlying model, run through this project's exact two-stage extraction with its loosely-enforced JSON schema, does not perform better here — it fails more often, and when it succeeds it frequently omits members it clearly had headroom to report. Because this is a `-preview` model, treat this figure as a point-in-time measurement, not something reproducible on demand.

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
