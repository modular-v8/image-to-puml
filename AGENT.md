# AGENT.md

Instructions for any AI coding agent working in this repository. Humans wanting to *use* the tool should read `README.md` instead — this file is about developing *on* it.

## General Rules
*Rules inspired from a Blog by Fabien Sanglard, [AGENT.md](https://fabiensanglard.net/agent.md/), which I came across recently.*

- When writing something intended for human consumption, (comment, commit message, reply to prompt) use as few words as possible. Pick every word meticulously to reduce the volume to a strict minimum. Be down to the point. Less is more.

- Avoid superlatives and praise. Stop telling me I am absolutely right. Give me the cold hard truth.

- Avoid magic numbers and strings by extracting recurring or meaningful values into descriptive constants (const) or enums. Keep self-explanatory, one-off values inline to avoid clutter. If a value comes from a spec (e.g. HTTP 200 OK), use a constant regardless.

- Reduce code indentation. Avoid Arrow Anti-Pattern. Leverage early return and continue.

- Keep function names short. Less than 30 characters.

- Let the reader of the code breathe. Add empty lines between logical blocks of code.

- Add a small, to the point, comment to explain *what* the block does and *why*. Use examples when possible. Propose ASCII drawings to explain complete systems.

- Treat member visibility changes as a breaking design shift. Keep all fields and functions private unless external access is strictly required by the design. Prompt the user for explicit approval before changing any access modifier from private to internal or public.

- Don't touch blocks of code unrelated to the feature you implement. e.g. Don't add comments to a block of code if you did not create it or modify it. As much as possible try to minimize the number of changed lines when implementing a feature.

- When you write a commit message, follow these 7 rules:
  - Rule 1: Separate the subject line from the body with a single blank line.
  - Rule 2: Limit the subject line to 50 characters (72 is the absolute hard limit).
  - Rule 3: Capitalize the first letter of the subject line.
  - Rule 4: Do not end the subject line with a period.
  - Rule 5: Use the imperative mood in the subject line (e.g., "Fix bug," "Add feature," 
        not "Fixed" or "Adds"). Test formula: It must complete the sentence: "If applied,
        this commit will [your subject line here]".
  - Rule 6: Wrap the body text manually at 72 characters to prevent Git formatting issues.
  - Rule 7: Use the body to explain what and why vs. how. Assume the code explains the how;
        the message must explain the context and reasoning. 

- If the prompt indicates that a bug is being fixed, don't write the fix right away. First write the test. Observe it failing. Then write the fix. And observe the test passing.     

## Tool Specific Rules

### Setup

```bash
uv python pin 3.12
uv sync
```

Python 3.12 is pinned deliberately — a newer interpreter may be present on the machine but lags on OpenCV/Pillow wheel availability. Don't change the pin without checking wheel availability first.

### Running tests

```bash
uv run pytest -q
```

This must pass with **no network access and no `OPENROUTER_API_KEY` set** — that's a hard project requirement, not a nice-to-have. If a test you're adding needs real network access, mark it `@pytest.mark.integration`; the default run excludes that marker (`pytest -m integration` is the only path that opts in). If a test needs to exercise the real render toolchain (java/dot/plantuml.jar), use the shared skip helper in `tests/unit/_toolchain.py` rather than writing a new ad-hoc `shutil.which("java")` check — a partial check (java only, not dot/jar) has caused real CI failures before.

Rendering tests need a JRE, Graphviz, and `tools/plantuml.jar` (gitignored, fetched separately — see README's install steps). If those aren't available locally, the relevant tests skip cleanly rather than failing.

### Live model calls cost real money and quota — treat them as a deliberate action, not a routine one

This project calls a real, metered AI provider (OpenRouter) for its core functionality. Before making a live call:
- **Say which model you're using** and roughly what it'll cost, before making the call.
- **Prefer the cache.** Every response is cached on disk keyed by image+prompt+model+params. Re-running the exact same call is free and instant (near-zero latency is how you can tell it was a cache hit, not a fresh call).
- **Don't chain multiple live calls silently.** One call, report the result, then decide on the next one — especially for anything beyond a single small diagram.
- The free-tier default (`google/gemma-4-26b-a4b-it:free`) rate-limits under load. For anything beyond a one-off interactive check, use `--model google/gemma-4-26b-a4b-it` (the paid tier of the same model) — it costs a fraction of a cent per call and has no rate limit.

### Never open, read, or print `.env`

It holds the real API key. Code in this repo (`cli.py`, various `scripts/*.py`) reads it programmatically at runtime via its own dotenv-loading logic — that's fine and expected. An agent using a file-reading tool to open `.env` directly, or echoing its contents to a shell, is not.

### Before committing or pushing

- Check what a broad `git add` actually staged (`git status`) before committing — this project has hit real near-misses with `.cache/`, `runs/`, and personal test-image files sitting untracked alongside real changes.
- Never commit `.env`, `.cache/`, `runs/`, or `tools/plantuml.jar` — all correctly gitignored already; don't force-add them.
- Run the full test suite before pushing, not just the tests you touched.
- Confirm with the user before pushing or tagging — this project's own working convention has been to treat any push, tag, or public-visibility change as needing an explicit go-ahead, not an assumed one.

### Architecture, briefly

```
image -> perception/ (talks to the model, returns a typed IR) -> generate/ (pure functions: IR -> .puml text, no I/O) -> render/ (shells out to plantuml.jar, optional)
```

- `ir/` defines the schema and a structural diff (`ir/diff.py`) used by both the evaluation scorer and the (disabled-by-default) self-verification loop. Change the schema carefully — both consumers depend on it.
- `generate/` must stay deterministic: the same IR always produces byte-identical `.puml`. Don't introduce anything time-based, random, or dict-ordering-dependent there.
- `perception/boxes.py` exists (bounding-box detection) but is **not called from the active pipeline** — see `FUTURE.md`. Don't wire it in without checking why it was left disabled first.

### Known environment gotchas (Windows)

- `uv tool install` / `uv tool uninstall` can fail mid-operation with a Windows file-lock error (`os error 32`) on native `.pyd` files, most likely from real-time antivirus scanning. If this happens, don't force-retry repeatedly or try to pause security software yourself — use `uvx --from <spec> <command>` instead, which runs from an isolated ephemeral cache and sidesteps the lock entirely.
- Editing `~/.bashrc` (or similar dotfiles) from a Windows GUI text editor can silently save it as UTF-16, which breaks Git Bash's ability to source it. If a shell environment variable you expect to be set isn't showing up, check the file's encoding before assuming the variable was never set.
- This tool runs Git Bash's `sh`, not PowerShell — commands and path syntax should target that shell unless a task specifically needs PowerShell (e.g., `Remove-Item` when a POSIX `rm` won't clear a Windows file lock).

### Where to look for more context

- `README.md` — what the tool does, how to install and use it, current accuracy figures.
- `FUTURE.md` — ideas deliberately deferred, and what would justify picking each one up.
- `RETROSPECTIVE.md` — lessons from building this, one page.
