"""Runtime configuration, resolved as environment < config file < CLI flag.

Each layer only supplies the fields it actually sets; a field absent from
every layer falls back to the Pydantic field's own default. API credentials
deliberately do NOT go through this precedence chain -- `OPENROUTER_API_KEY`
is read directly from the environment by the provider client, never from a
config file or CLI flag, so a shared config file can never leak or redirect
a key.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# Chosen per T2.6's preflight investigation (full findings table in
# README.md). Fast and cheap when it works, but not perfectly reliable
# (2/3 correct across live trials -- one hallucinated class, one malformed
# JSON response). `dots-studio/dots-3-note-preview:free` was 3/3 correct
# in the same trials and is the documented fallback if Gemma's failure
# rate turns out to matter once real extraction (T2.10+) is built on top
# of it -- no automatic fallback is wired up yet, this is a manual knob.
# Kept as the *interactive* default deliberately: a stranger's first run
# should be $0, per spec.md's audience note. See DEFAULT_EVAL_MODEL_ID for
# the model evaluation/eval-harness work uses instead, as of T3.36.
DEFAULT_MODEL_ID = "google/gemma-4-26b-a4b-it:free"

# T3.35/T3.36, 2026-08-18: the paid tier of the *same* model, not a
# different one -- isolates free-vs-paid serving as the only variable.
# Chosen over the free default for all evaluation and scored-comparison
# work after T3.35's noise-floor run found the free tier degrading badly
# under sustained load (two of five characterization runs failed
# outright on rate limits) while the paid tier's one completed run beat
# every free-tier run's observed range on class recall and kind accuracy,
# with zero short/incomplete responses. User-confirmed 2026-08-18: use
# the paid tier from here on for anything that needs a reliable result,
# given the cost is negligible (~$0.07 per million tokens).
DEFAULT_EVAL_MODEL_ID = "google/gemma-4-26b-a4b-it"

# OpenRouter's stated free-tier cap. The client throttles to this rate
# proactively (spacing requests) rather than relying solely on reactive
# 429 retries -- see OpenRouterClient. Paid-model runs, which carry no
# OpenRouter-enforced limit, should override this higher (or the caller
# can pass a large value to effectively disable throttling).
DEFAULT_REQUESTS_PER_MINUTE = 20.0

# T4.16, 2026-08-20: calibrated against the shipped configuration's actual
# confidence distribution (corpus + holdout, 58 relationships), not chosen
# a priori like the original 0.7. The distribution turned out fully
# bimodal -- {0.0: 3, 0.5: 55} -- because extraction only ever assigns one
# of two placeholder values (extract.py's _PLACEHOLDER_CONFIDENCE /
# _NO_EVIDENCE_CONFIDENCE); no real per-relationship confidence signal
# exists (the two sources that would have provided one, the per-connector
# crop pass and the verification loop, were respectively cut and shipped
# disabled -- see README). The original 0.7 sits *above* the 0.5
# placeholder, so it flagged all 58/58 relationships regardless of
# correctness: precision 21% (the flat base rate), zero filtering value --
# exactly the "flags nearly everything" failure this calibration exists to
# catch. 0.3 (matching verify/requery.py's existing REQUERY_CONFIDENCE,
# for one consistent "below normal trust" line across the codebase) flags
# only the 3 zero-confidence relationships instead of all 58. Their
# measured precision was 0% (0/3 actually wrong) -- but at n=3 that's not
# a real signal either way, just too small a sample to draw a conclusion
# from. The honest summary: this is the least-bad available threshold,
# not a validated one -- no value can be well-calibrated until a real
# per-relationship confidence source exists. Full analysis in
# scripts/calibrate_confidence.py and tasks.md T4.16.
DEFAULT_CONFIDENCE_THRESHOLD = 0.3

_ENV_PREFIX = "UMLREGEN_"


class Config(BaseModel):
    model_id: str = DEFAULT_MODEL_ID
    eval_model_id: str = DEFAULT_EVAL_MODEL_ID
    cache_dir: Path = Path(".cache")
    confidence_threshold: float = Field(default=DEFAULT_CONFIDENCE_THRESHOLD, ge=0.0, le=1.0)
    verification_max_rounds: int = Field(default=2, ge=0)
    render_format: Literal["svg", "png", "pdf"] = "svg"
    requests_per_minute: float = Field(default=DEFAULT_REQUESTS_PER_MINUTE, gt=0.0)


_ENV_VARS = {
    "model_id": f"{_ENV_PREFIX}MODEL_ID",
    "eval_model_id": f"{_ENV_PREFIX}EVAL_MODEL_ID",
    "cache_dir": f"{_ENV_PREFIX}CACHE_DIR",
    "confidence_threshold": f"{_ENV_PREFIX}CONFIDENCE_THRESHOLD",
    "verification_max_rounds": f"{_ENV_PREFIX}VERIFICATION_MAX_ROUNDS",
    "render_format": f"{_ENV_PREFIX}RENDER_FORMAT",
    "requests_per_minute": f"{_ENV_PREFIX}REQUESTS_PER_MINUTE",
}


def _from_env() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, env_var in _ENV_VARS.items():
        raw = os.environ.get(env_var)
        if raw is not None:
            values[field] = raw
    return values


def _from_config_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if k in Config.model_fields}


def load_config(
    *,
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> Config:
    """Resolves a `Config` from environment, an optional TOML config file,
    and optional CLI-flag overrides -- later layers win field-by-field.
    """
    merged: dict[str, Any] = {}
    merged.update(_from_env())
    merged.update(_from_config_file(config_path))
    if cli_overrides:
        merged.update({k: v for k, v in cli_overrides.items() if v is not None})
    return Config.model_validate(merged)
