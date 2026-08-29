"""T4.6: offline CLI tests. No network, no API key -- `_build_client` is
monkeypatched to return a scripted `VisionClient` (or a raising stub),
the same technique `test_api.py`/`test_reliability.py` use one layer
down. `image` arguments point at a throwaway file; nothing here parses
image bytes as real image data (T4.12's input validation is Day 16, not
yet built), so a dummy file is sufficient.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from typer.testing import CliRunner

from umlregen import cli
from umlregen.errors import (
    DependencyMissing,
    ExtractionInvalid,
    NoClassesFound,
    ProviderAuthError,
    ProviderRateLimited,
    RenderFailed,
    RepetitionDetected,
    ResponseTruncated,
    UmlRegenError,
)
from umlregen.perception.client import VisionResponse

from _toolchain import requires_render_toolchain as requires_java

runner = CliRunner()

_STAGE_A_TWO_CLASSES = {
    "classes": [
        {"name": "Foo", "kind": "class", "attributes": [], "methods": []},
        {"name": "Bar", "kind": "class", "attributes": [], "methods": []},
    ],
    "relationships": [],
}
_STAGE_B_ONE_RELATIONSHIP = {
    "relationships": [
        {"source": "Foo", "target": "Bar", "kind": "association", "evidence": "solid line"}
    ]
}
_STAGE_A_EMPTY = {"classes": [], "relationships": []}


class _ScriptedClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        return self._responses.pop(0)


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        raise self._exc


def _dummy_image(tmp_path: Path) -> Path:
    # A genuinely valid (tiny) PNG, saved under a .jpg-named path -- T4.12's
    # validate_image() checks decoded content, not the file extension, so
    # this still passes while keeping with_suffix(...) checks on the
    # *output* meaningful instead of trivially matching the input.
    path = tmp_path / "diagram.jpg"
    Image.new("RGB", (10, 10), color="white").save(path, format="PNG")
    return path


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # No network, no key: every test supplies its own client via
    # _build_client monkeypatching rather than relying on env state.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    monkeypatch.setattr(cli, "_build_client", lambda *args, **kwargs: client)


# ---------------------------------------------------------------------------
# T4.1: the app itself
# ---------------------------------------------------------------------------


def test_help_lists_all_four_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for name in ("run", "eval", "corpus", "doctor"):
        assert name in result.output


# ---------------------------------------------------------------------------
# T4.2: `run` flag behavior
# ---------------------------------------------------------------------------


def test_run_without_render_produces_puml_and_no_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # T7.1: default output is CWD-relative (output/<stem>/)
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)

    result = runner.invoke(cli.app, ["run", str(image)])

    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "output" / image.stem
    puml_path = run_dir / f"{image.stem}.puml"
    assert puml_path.is_file()
    assert "Foo" in puml_path.read_text(encoding="utf-8")
    assert not (run_dir / f"{image.stem}.svg").is_file()
    assert not (run_dir / f"{image.stem}.png").is_file()


@requires_java
def test_run_with_render_svg_produces_exactly_that_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # T7.1: chdir'ing to tmp_path (for output-location isolation) breaks
    # plantuml.jar's default CWD-relative resolution, since the actual
    # render call happens after the chdir -- point at the real jar's
    # absolute path first, exactly as a standalone-tool user would per
    # the README's UMLREGEN_PLANTUML_JAR instructions.
    monkeypatch.setenv("UMLREGEN_PLANTUML_JAR", str(Path("tools/plantuml.jar").resolve()))
    monkeypatch.chdir(tmp_path)
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)

    result = runner.invoke(cli.app, ["run", str(image), "--render", "svg"])

    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "output" / image.stem
    assert (run_dir / f"{image.stem}.svg").is_file()
    assert not (run_dir / f"{image.stem}.png").is_file()
    assert not (run_dir / f"{image.stem}.pdf").is_file()


def test_run_output_flag_overrides_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # T7.1: -o must override the output/<stem>/ default entirely, not just
    # the old next-to-the-image default -- so this also chdirs and checks
    # that no output/ directory gets created anywhere at all.
    monkeypatch.chdir(tmp_path)
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)
    custom_out = tmp_path / "somewhere" / "custom.puml"

    result = runner.invoke(cli.app, ["run", str(image), "-o", str(custom_out)])

    assert result.exit_code == 0, result.output
    assert custom_out.is_file()
    assert not image.with_suffix(".puml").is_file()
    assert (custom_out.parent / "custom.review.md").is_file()
    assert (custom_out.parent / "custom.ir.json").is_file()
    assert (custom_out.parent / "run.json").is_file()
    assert not (tmp_path / "output").exists()


def test_run_default_output_creates_the_full_layout_under_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7.1: default layout is output/<stem>/{<stem>.puml, .review.md, .ir.json, run.json}."""
    monkeypatch.chdir(tmp_path)
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model", cost_usd=0.001),
            VisionResponse(
                raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model", cost_usd=0.002
            ),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)

    result = runner.invoke(cli.app, ["run", str(image), "--model", "test/model"])

    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "output" / image.stem
    assert run_dir.is_dir()
    assert (run_dir / f"{image.stem}.puml").is_file()
    assert (run_dir / f"{image.stem}.review.md").is_file()

    ir_path = run_dir / f"{image.stem}.ir.json"
    assert ir_path.is_file()
    ir_data = json.loads(ir_path.read_text(encoding="utf-8"))
    assert [c["name"] for c in ir_data["classes"]] == ["Foo", "Bar"]

    run_json_path = run_dir / "run.json"
    assert run_json_path.is_file()
    run_json_text = run_json_path.read_text(encoding="utf-8")
    run_data = json.loads(run_json_text)
    # Whitelisted fields only -- see cli.py's own comment on why this must
    # never be a wholesale dump of `config`.
    assert set(run_data.keys()) == {"model_id", "cost_usd", "duration_seconds", "warnings", "timestamp"}
    assert run_data["model_id"] == "test/model"
    assert run_data["cost_usd"] == pytest.approx(0.003)
    assert "OPENROUTER_API_KEY" not in run_json_text
    assert "sk-" not in run_json_text  # a plausible key-shaped substring, just in case


def test_run_default_output_writes_nothing_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7.1's actual complaint, asserted directly: nothing lands in cwd any more."""
    monkeypatch.chdir(tmp_path)
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)  # lives directly in tmp_path -- i.e. "the working directory"

    before = set(tmp_path.iterdir())
    result = runner.invoke(cli.app, ["run", str(image)])
    assert result.exit_code == 0, result.output

    new_entries = set(tmp_path.iterdir()) - before
    assert new_entries == {tmp_path / "output"}, f"unexpected new entries directly in cwd: {new_entries}"


def test_run_verify_off_by_default_never_calls_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # T7.1: this run succeeds through to the write step
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)

    called = {"count": 0}
    monkeypatch.setattr(cli, "verify", lambda *a, **k: called.__setitem__("count", called["count"] + 1))

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path))])

    assert result.exit_code == 0, result.output
    assert called["count"] == 0


def test_run_verify_flag_calls_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from umlregen.verify.loop import VerifyResult, VerifyStats

    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)

    called = {"count": 0}

    def _fake_verify(diagram, client, *, max_rounds, debug_dir):
        called["count"] += 1
        return VerifyResult(diagram=diagram, stats=VerifyStats(rounds_run=1, converged=True))

    monkeypatch.setattr(cli, "verify", _fake_verify)

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path)), "--verify"])

    assert result.exit_code == 0, result.output
    assert called["count"] == 1


# ---------------------------------------------------------------------------
# T4.10 / T7.2: end-to-end determinism at the CLI boundary, and the
# cache-default change T7.2 made to it.
# ---------------------------------------------------------------------------


class _CountingClient:
    def __init__(self, responses: list[VisionResponse]) -> None:
        self._responses = list(responses)
        self.call_log: list[str] = []

    def complete(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> VisionResponse:
        self.call_log.append(prompt)
        return self._responses.pop(0)


def _two_stage_responses() -> list[VisionResponse]:
    return [
        VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
        VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
    ]


def test_run_twice_with_reuse_cache_flag_produces_byte_identical_puml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7.2: `--reuse-cache` is the only way `run` now reaches the old
    "warm cache" behavior -- this test exercises exactly that opt-in path,
    not the default (see the sibling test below for the default)."""
    from umlregen.perception.cache import CachedVisionClient

    inner = _CountingClient(_two_stage_responses())
    # A real CachedVisionClient, not a scripted stand-in -- this is the
    # actual caching layer `run --reuse-cache` uses in production, pointed
    # at a throwaway directory so "warm cache" here means the same thing
    # it means for a real user re-running the CLI with the flag set.
    # force_refresh=False matches what `--reuse-cache` wires up in cli.py.
    cached_client = CachedVisionClient(
        inner, model_id="test/model", cache_dir=tmp_path / "cache", force_refresh=False
    )
    monkeypatch.setattr(cli, "_build_client", lambda *a, **k: cached_client)

    image = _dummy_image(tmp_path)
    out1 = tmp_path / "run1.puml"
    out2 = tmp_path / "run2.puml"

    result1 = runner.invoke(cli.app, ["run", str(image), "-o", str(out1), "--reuse-cache"])
    assert result1.exit_code == 0, result1.output
    result2 = runner.invoke(cli.app, ["run", str(image), "-o", str(out2), "--reuse-cache"])
    assert result2.exit_code == 0, result2.output

    assert out1.read_bytes() == out2.read_bytes()
    # Exactly stage A + stage B, once -- the second `run` never touched
    # the underlying client at all, proving cache reuse rather than
    # merely coincidentally-identical fresh output.
    assert len(inner.call_log) == 2


def test_run_twice_by_default_makes_two_full_sets_of_fresh_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7.2's actual behavior change: without `--reuse-cache`, a second
    `run` on the same image must NOT be served from cache -- this is the
    test that would have caught the incident (one bad cached response
    silently replayed on every later run) had it existed beforehand."""
    from umlregen.perception.cache import CachedVisionClient

    inner = _CountingClient(_two_stage_responses() + _two_stage_responses())
    # force_refresh=True matches what `run`'s new default wires up in
    # cli.py -- constructed directly (rather than going through
    # `_build_client`) so this test exercises `CachedVisionClient`'s own
    # force-refresh behavior without depending on flag parsing, which the
    # kwargs-capturing test below covers separately.
    cached_client = CachedVisionClient(
        inner, model_id="test/model", cache_dir=tmp_path / "cache", force_refresh=True
    )
    monkeypatch.setattr(cli, "_build_client", lambda *a, **k: cached_client)

    image = _dummy_image(tmp_path)
    out1 = tmp_path / "run1.puml"
    out2 = tmp_path / "run2.puml"

    result1 = runner.invoke(cli.app, ["run", str(image), "-o", str(out1)])
    assert result1.exit_code == 0, result1.output
    result2 = runner.invoke(cli.app, ["run", str(image), "-o", str(out2)])
    assert result2.exit_code == 0, result2.output

    # Stage A + stage B, twice -- every explicit invocation pays for a
    # fresh answer, even though it's a repeat of one already cached.
    assert len(inner.call_log) == 4
    assert cached_client.cache_hits == 0
    assert cached_client.cache_misses == 4


def test_run_default_wires_force_refresh_true_into_build_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag-parsing half: `run` with no cache flag must ask
    `_build_client` for `force_refresh=True`."""
    captured: dict[str, Any] = {}

    def _capturing_build_client(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return _ScriptedClient(_two_stage_responses())

    monkeypatch.setattr(cli, "_build_client", _capturing_build_client)

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path))])

    assert result.exit_code == 0, result.output
    assert captured["force_refresh"] is True


def test_run_reuse_cache_flag_wires_force_refresh_false_into_build_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def _capturing_build_client(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return _ScriptedClient(_two_stage_responses())

    monkeypatch.setattr(cli, "_build_client", _capturing_build_client)

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path)), "--reuse-cache"])

    assert result.exit_code == 0, result.output
    assert captured["force_refresh"] is False


def test_run_verbose_reports_cache_hits_when_reuse_cache_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7.2's visibility requirement: a cache hit must say so under -v --
    silence here is exactly what let the incident go unnoticed. Genuine
    end-to-end, no hand-matched prompt text: the first invocation writes
    the cache (default, force_refresh=True), the second reads it back
    (--reuse-cache) -- both share the same real cache_dir and image, so
    the keys line up naturally rather than being asserted by construction.
    """
    from umlregen.perception.cache import CachedVisionClient

    cache_dir = tmp_path / "cache"

    def _fresh_client(*args: Any, **kwargs: Any) -> CachedVisionClient:
        raw = _ScriptedClient(_two_stage_responses())
        return CachedVisionClient(
            raw,
            model_id="test/model",
            cache_dir=cache_dir,
            force_refresh=kwargs.get("force_refresh", False),
        )

    monkeypatch.setattr(cli, "_build_client", _fresh_client)
    image = _dummy_image(tmp_path)

    first = runner.invoke(cli.app, ["run", str(image), "-o", str(tmp_path / "r1.puml")])
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        cli.app, ["run", str(image), "-o", str(tmp_path / "r2.puml"), "--reuse-cache", "-v"]
    )
    assert second.exit_code == 0, second.output
    assert "Cache: 2 response(s) served from cache, 0 fresh call(s)." in second.output


# ---------------------------------------------------------------------------
# T4.4: exit-code mapping, one representative case per error class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        ProviderAuthError("OpenRouter rejected the API key (401)"),
        ProviderRateLimited("rate limited"),
        ExtractionInvalid("bad json", raw_response="not json"),
        ResponseTruncated("truncated twice", raw_response="...", token_cap=12000),
        RepetitionDetected("looping", raw_response="..."),
    ],
)
def test_run_maps_perception_errors_to_their_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: UmlRegenError
) -> None:
    _patch_client(monkeypatch, _RaisingClient(exc))

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path))])

    assert result.exit_code == exc.exit_code
    assert "Error:" in result.output


def test_run_maps_no_classes_found_to_its_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Two empty stage-A responses: original attempt + T4.19's reframed
    # retry, both empty -> extract_classes raises ExtractionDeclined,
    # which regenerate() translates to NoClassesFound.
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
            VisionResponse(raw_text="still nothing", parsed_json=_STAGE_A_EMPTY, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path))])

    assert result.exit_code == NoClassesFound.exit_code


def test_run_maps_render_failed_to_its_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # T7.1: succeeds through .puml/.review.md/.ir.json before render fails
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=_STAGE_A_TWO_CLASSES, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json=_STAGE_B_ONE_RELATIONSHIP, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    exc = RenderFailed("render failed", puml_source="@startuml\n@enduml", stderr="boom")
    monkeypatch.setattr(cli, "render_puml", lambda *a, **k: (_ for _ in ()).throw(exc))

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path)), "--render", "svg"])

    assert result.exit_code == RenderFailed.exit_code


def test_doctor_maps_dependency_missing_to_exit_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = DependencyMissing("Required tool 'dot' was not found")
    monkeypatch.setattr(cli, "render_preflight", lambda *a, **k: (_ for _ in ()).throw(exc))

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == DependencyMissing.exit_code
    assert "dot" in result.output


@requires_java
def test_doctor_succeeds_with_dependencies_present() -> None:
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "OK" in result.output


# ---------------------------------------------------------------------------
# T4.3: no key material ever appears in output
# ---------------------------------------------------------------------------


def test_provider_auth_error_never_echoes_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _RaisingClient(ProviderAuthError("OpenRouter rejected the API key (401)")))

    result = runner.invoke(cli.app, ["run", str(_dummy_image(tmp_path))])

    assert "sk-" not in result.output  # a plausible key-shaped substring, just in case
    assert result.exit_code == ProviderAuthError.exit_code


# ---------------------------------------------------------------------------
# T4.12: a model-supplied class name can never influence a file location
# ---------------------------------------------------------------------------


def test_malicious_class_name_cannot_escape_the_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malicious_stage_a = {
        "classes": [
            {"name": "../../../../etc/evil", "kind": "class", "attributes": [], "methods": []},
            {"name": "C:\\Windows\\System32\\evil", "kind": "class", "attributes": [], "methods": []},
        ],
        "relationships": [],
    }
    client = _ScriptedClient(
        [
            VisionResponse(raw_text="ok", parsed_json=malicious_stage_a, model_id="test/model"),
            VisionResponse(raw_text="ok", parsed_json={"relationships": []}, model_id="test/model"),
        ]
    )
    _patch_client(monkeypatch, client)
    image = _dummy_image(tmp_path)
    out_path = tmp_path / "out" / "diagram.puml"

    result = runner.invoke(cli.app, ["run", str(image), "-o", str(out_path)])

    assert result.exit_code == 0, result.output
    # Only the expected files exist, exactly where -o and the sidecar
    # convention (T4.7, extended by T7.1's .ir.json/run.json) say they
    # should -- nothing escaped tmp_path, and the malicious raw names
    # never became path components anywhere.
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == sorted(
        [
            image.relative_to(tmp_path).as_posix(),
            "out/diagram.puml",
            "out/diagram.review.md",
            "out/diagram.ir.json",
            "out/run.json",
        ]
    )
    # The class *does* appear in the .puml content (as a sanitized alias
    # and a quoted display name), just never as a filesystem path.
    puml_text = out_path.read_text(encoding="utf-8")
    assert ".." not in puml_text.split("\n", 1)[0]  # no traversal sequence leaked into e.g. an alias


# ---------------------------------------------------------------------------
# `corpus`: CLI plumbing only, build_corpus() itself is tested elsewhere
# ---------------------------------------------------------------------------


def test_corpus_command_calls_build_corpus_and_prints_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda: [Path("corpus/img/a.png"), Path("corpus/img/b.png")])

    result = runner.invoke(cli.app, ["corpus"])

    assert result.exit_code == 0
    assert "a.png" in result.output
    assert "b.png" in result.output


# ---------------------------------------------------------------------------
# `eval`: scored + failed diagrams both surface correctly
# ---------------------------------------------------------------------------


def test_eval_command_reports_scorecard_and_failure_breakdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from umlregen.eval.runner import DiagramResult, EvalRunResult
    from umlregen.eval.score import score
    from umlregen.ir.models import Diagram

    diagram = Diagram(classes=[], relationships=[])
    fake_result = EvalRunResult(
        scored=[DiagramResult(name="ok_one", score=score(diagram, diagram), cost_usd=0.001, latency_seconds=0.1, warning_count=0)],
        failures=[("bad_one", "decline")],
    )
    # T5.7: _build_client must be mocked too, not just run_eval_set -- it's
    # called unconditionally before run_eval_set and constructs a real
    # OpenRouterClient, which raises ProviderAuthError with no key present.
    # This test previously passed locally only because cli.py's per-command
    # _load_dotenv() re-populated OPENROUTER_API_KEY from this repo's local
    # .env file (via os.environ.setdefault) even after the autouse
    # _no_env_key fixture deleted it -- CI, with no .env file checked out,
    # exposed that the "offline, no key" guarantee was never actually true
    # for this one test.
    _patch_client(monkeypatch, object())
    monkeypatch.setattr(cli, "run_eval_set", lambda *a, **k: fake_result)
    monkeypatch.setattr(cli, "append_run_log", lambda *a, **k: None)
    monkeypatch.setattr(cli, "append_failure_log", lambda *a, **k: None)

    result = runner.invoke(cli.app, ["eval"])

    assert result.exit_code == 0, result.output
    assert "Scorecard" in result.output
    assert "bad_one" in result.output
    assert "decline" in result.output
