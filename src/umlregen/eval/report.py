"""Human-readable scorecards, and a persistent run log so accuracy over
time survives for the write-up -- appended to, never overwritten.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from umlregen.errors import ExtractionDeclined, ExtractionInvalid, RepetitionDetected, ResponseTruncated
from umlregen.eval.score import ScoreResult

_DEFAULT_LOG_PATH = Path("runs/run_log.jsonl")

# T4.20: the three modes T3.28 diagnosed from real ceiling-experiment
# responses, plus the pre-existing catch-all for genuinely unparseable
# output (T2.12) -- one exception type per mode, so classification is a
# straight isinstance check rather than string-matching a message.
FAILURE_MODES = ("truncation", "repetition", "decline", "unparseable")


def classify_failure(exc: BaseException) -> str:
    """Maps a raised extraction exception to one of `FAILURE_MODES`, or
    `"other"` for anything not part of T3.28's diagnosed taxonomy."""
    if isinstance(exc, ResponseTruncated):
        return "truncation"
    if isinstance(exc, RepetitionDetected):
        return "repetition"
    if isinstance(exc, ExtractionDeclined):
        return "decline"
    if isinstance(exc, ExtractionInvalid):
        return "unparseable"
    return "other"

_METRIC_LABELS: dict[str, str] = {
    "class_recall": "Class recall",
    "class_precision": "Class precision",
    "class_f1": "Class F1",
    "member_f1": "Member F1",
    "relationship_f1": "Relationship F1",
    "pair_recall": "Pair recall",
    "kind_accuracy_given_correct_pair": "Kind accuracy (given correct pair)",
}


def aggregate_scores(results: list[ScoreResult]) -> ScoreResult:
    """Mean of each metric across `results` -- one number per diagram,
    macro-averaged into one number for the corpus. Simple and legible; a
    diagram with zero relationships doesn't silently vanish from a pooled
    denominator the way micro-averaging would let it.
    """
    if not results:
        raise ValueError("cannot aggregate an empty list of results")
    fields = list(ScoreResult.model_fields)
    return ScoreResult(
        **{
            field: sum(getattr(r, field) for r in results) / len(results)
            for field in fields
        }
    )


def format_scorecard(result: ScoreResult, *, title: str = "Scorecard") -> str:
    lines = [title, "-" * len(title)]
    for field, label in _METRIC_LABELS.items():
        value = getattr(result, field)
        lines.append(f"{label:<36} {value:.1%}")
    return "\n".join(lines)


def append_run_log(
    result: ScoreResult,
    *,
    model_id: str,
    cost_usd: float,
    latency_seconds: float,
    warning_count: int,
    log_path: Path = _DEFAULT_LOG_PATH,
    timestamp: datetime | None = None,
) -> None:
    """Appends exactly one JSON-lines row to `log_path`, creating the file
    (and its parent directory) if needed. Never overwrites -- run history
    is meant to accumulate, so accuracy-over-time survives for the
    write-up.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "model_id": model_id,
        "cost_usd": cost_usd,
        "latency_seconds": latency_seconds,
        "warning_count": warning_count,
        **result.model_dump(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def append_failure_log(
    *,
    diagram_name: str,
    model_id: str,
    mode: str,
    message: str,
    log_path: Path = _DEFAULT_LOG_PATH,
    timestamp: datetime | None = None,
) -> None:
    """T4.20: appends one JSON-lines row per failed diagram to the same
    log the other `append_*` functions use, naming which of
    `FAILURE_MODES` it hit -- so a run's failure rate becomes a breakdown
    by cause, not just a bare denominator.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "run_type": "failure",
        "model_id": model_id,
        "diagram": diagram_name,
        "mode": mode,
        "message": message,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def format_failure_breakdown(failures: list[tuple[str, str]], *, title: str = "Failure breakdown") -> str:
    """`failures` is a list of `(diagram_name, mode)` pairs. Prints a count
    per mode (zero-filled for modes that didn't occur) followed by which
    diagram hit each one, so the breakdown names causes, not just counts.
    """
    lines = [title, "-" * len(title)]
    counts = {mode: 0 for mode in FAILURE_MODES}
    by_mode: dict[str, list[str]] = {mode: [] for mode in FAILURE_MODES}
    other: list[str] = []
    for diagram_name, mode in failures:
        if mode in counts:
            counts[mode] += 1
            by_mode[mode].append(diagram_name)
        else:
            other.append(diagram_name)

    for mode in FAILURE_MODES:
        lines.append(f"{mode:<13} {counts[mode]:>3}  {', '.join(by_mode[mode]) or '-'}")
    if other:
        lines.append(f"{'other':<13} {len(other):>3}  {', '.join(other)}")
    lines.append(f"{'total failed':<13} {len(failures):>3}")
    return "\n".join(lines)


def append_verify_log(
    *,
    model_id: str,
    rounds_run: int,
    converged: bool,
    render_reextract_calls: int,
    requery_calls: int,
    rejected_patch_count: int,
    render_reextract_cost_usd: float,
    requery_cost_usd: float,
    latency_seconds: float,
    log_path: Path = _DEFAULT_LOG_PATH,
    timestamp: datetime | None = None,
) -> None:
    """T3.23: appends one JSON-lines row for a `verify()` run to the same
    log `append_run_log` writes to, so run history stays in one place.
    Takes plain fields rather than `VerifyStats` directly, to avoid
    `eval/` depending on `verify/` -- `report.py` stays a leaf module
    either way. Distinguishable from a scoring row by its `run_type` and
    the absence of any accuracy metric field -- `verify()`'s effect *on*
    accuracy is what T3.24's scored `--verify` vs `--no-verify`
    comparison measures, through the normal scoring path, not this log.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "run_type": "verify",
        "model_id": model_id,
        "rounds_run": rounds_run,
        "converged": converged,
        "render_reextract_calls": render_reextract_calls,
        "requery_calls": requery_calls,
        "total_calls": render_reextract_calls + requery_calls,
        "rejected_patch_count": rejected_patch_count,
        "render_reextract_cost_usd": render_reextract_cost_usd,
        "requery_cost_usd": requery_cost_usd,
        "total_cost_usd": render_reextract_cost_usd + requery_cost_usd,
        "latency_seconds": latency_seconds,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
