"""Offline tests for eval/report.py (T2.19): the scorecard prints all
five spec-named metrics, the run log appends exactly one row per call
(never overwrites), and aggregation computes a correct mean."""

import json
from pathlib import Path

from umlregen.eval.report import aggregate_scores, append_run_log, format_scorecard
from umlregen.eval.score import ScoreResult

_SPEC_NAMED_METRICS = [
    "Class recall",
    "Member F1",
    "Relationship F1",
    "Pair recall",
    "Kind accuracy",
]

_SAMPLE = ScoreResult(
    class_recall=0.9,
    class_precision=0.8,
    class_f1=0.85,
    member_f1=0.7,
    relationship_f1=0.6,
    pair_recall=0.75,
    kind_accuracy_given_correct_pair=0.5,
)


def test_scorecard_prints_all_five_spec_named_metrics() -> None:
    text = format_scorecard(_SAMPLE)
    for label in _SPEC_NAMED_METRICS:
        assert label in text


def test_append_run_log_writes_exactly_one_row(tmp_path: Path) -> None:
    log_path = tmp_path / "run_log.jsonl"

    append_run_log(
        _SAMPLE,
        model_id="test/model",
        cost_usd=0.001,
        latency_seconds=2.5,
        warning_count=3,
        log_path=log_path,
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["model_id"] == "test/model"
    assert row["cost_usd"] == 0.001
    assert row["warning_count"] == 3
    assert row["class_recall"] == 0.9


def test_append_run_log_never_overwrites(tmp_path: Path) -> None:
    log_path = tmp_path / "run_log.jsonl"

    for _ in range(3):
        append_run_log(
            _SAMPLE, model_id="test/model", cost_usd=0.0,
            latency_seconds=1.0, warning_count=0, log_path=log_path,
        )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_append_run_log_creates_parent_directory(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "dir" / "run_log.jsonl"

    append_run_log(
        _SAMPLE, model_id="test/model", cost_usd=0.0,
        latency_seconds=1.0, warning_count=0, log_path=log_path,
    )

    assert log_path.is_file()


def test_aggregate_scores_computes_the_mean() -> None:
    a = ScoreResult(
        class_recall=1.0, class_precision=1.0, class_f1=1.0,
        member_f1=1.0, relationship_f1=1.0, pair_recall=1.0,
        kind_accuracy_given_correct_pair=1.0,
    )
    b = ScoreResult(
        class_recall=0.0, class_precision=0.0, class_f1=0.0,
        member_f1=0.0, relationship_f1=0.0, pair_recall=0.0,
        kind_accuracy_given_correct_pair=0.0,
    )

    result = aggregate_scores([a, b])

    assert result.class_recall == 0.5
    assert result.member_f1 == 0.5
    assert result.kind_accuracy_given_correct_pair == 0.5
