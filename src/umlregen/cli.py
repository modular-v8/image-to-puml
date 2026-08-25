"""The `uml-regen` CLI: a thin `typer` app dispatching to `api.py`,
`eval/`, `render/`, and `verify/` -- no pipeline logic lives here, only
argument parsing, output formatting, and the exception-to-exit-code
mapping (T4.4). See plan.md's Architecture: `api.py` is the single seam.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from umlregen.api import regenerate
from umlregen.config import load_config
from umlregen.errors import UmlRegenError
from umlregen.eval.corpus import build_corpus
from umlregen.eval.report import (
    aggregate_scores,
    append_failure_log,
    append_run_log,
    format_failure_breakdown,
    format_scorecard,
)
from umlregen.eval.runner import run_eval_set
from umlregen.generate.puml import ir_to_puml
from umlregen.generate.review import write_review
from umlregen.input_validation import validate_image
from umlregen.perception.cache import CachedVisionClient
from umlregen.perception.client import VisionClient
from umlregen.perception.openrouter import OpenRouterClient
from umlregen.render.plantuml import preflight as render_preflight
from umlregen.render.plantuml import render as render_puml
from umlregen.verify.loop import verify

app = typer.Typer(
    add_completion=False,
    help="Reproduce UML class diagrams from images into editable PlantUML source.",
)


def _load_dotenv() -> None:
    """Loads `.env` from the current directory into `os.environ`, same
    parsing as the project's eval scripts -- real environment variables
    always win (`setdefault`), so this only fills gaps. Keeps
    `OPENROUTER_API_KEY` findable via the conventional `.env` file
    without the CLI depending on a third-party dotenv library for one
    small parsing loop.
    """
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


@app.callback()
def _main() -> None:
    _load_dotenv()


class RenderFormat(str, Enum):
    svg = "svg"
    png = "png"
    pdf = "pdf"


def _fail(exc: UmlRegenError) -> None:
    """T4.4: the one place a typed error becomes console output and an
    exit code -- every command routes its `UmlRegenError`s through this,
    so the mapping can't drift between commands. Never prints the raw
    exception repr for `ProviderAuthError`; its own message is already
    scrubbed of key material at the source (openrouter.py).
    """
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=exc.exit_code)


def _run_output_dir(image: Path) -> Path:
    """T7.1: the default per-run output location, `output/<image-stem>/`.
    `output/` is gitignored -- these are regenerable run artifacts, not
    source. Kept as a single-purpose helper so the default location is
    computed the same way everywhere it's needed (the .puml default and
    the --debug-dir default), rather than duplicated inline.
    """
    return Path("output") / image.stem


def _build_client(
    model_id: str,
    cache_dir: Path,
    requests_per_minute: float,
    *,
    no_cache: bool,
    repetition_retry_attempts: int = 1,
) -> VisionClient:
    raw = OpenRouterClient(
        model_id=model_id,
        requests_per_minute=requests_per_minute,
        repetition_retry_attempts=repetition_retry_attempts,
    )
    if no_cache:
        return raw
    return CachedVisionClient(raw, model_id=model_id, cache_dir=cache_dir)


@app.command()
def run(
    image: Path = typer.Argument(..., exists=True, dir_okay=False, help="Path to the diagram image (PNG/JPG)."),
    output: Optional[Path] = typer.Option(
        None,
        "-o",
        "--output",
        help="Where to write the .puml file. Defaults to output/<image-stem>/<image-stem>.puml. "
        "Overrides the default location entirely -- sidecar files (.review.md, .ir.json, run.json, "
        "and any rendered image) are written next to it, not under output/.",
    ),
    render_format: Optional[RenderFormat] = typer.Option(
        None, "--render", help="Also render the .puml to this format. Omit to produce .puml only, no image."
    ),
    verify_flag: bool = typer.Option(
        False,
        "--verify/--no-verify",
        help=(
            "Run the round-trip verification pass (render, re-extract, diff, targeted "
            "re-query). OFF BY DEFAULT: measured to make relationship F1 worse, not "
            "better, on both evaluation sets (see README \"What this project found\"). "
            "Ships present so that negative result is reproducible, not because it is "
            "recommended."
        ),
    ),
    model: Optional[str] = typer.Option(None, "--model", help="Override the configured vision model id."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the response cache entirely (no read, no write)."),
    debug_dir: Optional[Path] = typer.Option(
        None,
        "--debug-dir",
        help="Directory for verification's intermediate renders. Only used with --verify. "
        "Defaults to output/<image-stem>/debug/.",
    ),
    verbose: int = typer.Option(0, "-v", "--verbose", count=True, help="Increase output detail. Repeatable: -v, -vv."),
) -> None:
    """Regenerate one image into editable PlantUML source."""
    config = load_config(cli_overrides={"model_id": model})
    client = _build_client(
        config.model_id,
        config.cache_dir,
        config.requests_per_minute,
        no_cache=no_cache,
        repetition_retry_attempts=config.repetition_retry_attempts,
    )

    # T7.1: output/<image-stem>/ is the default run location -- nothing
    # lands in the working directory any more. -o overrides it completely
    # (a user-specified path is honoured exactly, no output/ prefix
    # injected); --debug-dir's own default follows the same convention
    # unconditionally, since debug artifacts belong to the run/input, not
    # to wherever -o happens to redirect the .puml.
    run_dir = _run_output_dir(image)
    effective_debug_dir = debug_dir if debug_dir is not None else (run_dir / "debug")

    try:
        image_bytes = validate_image(image)
        result = regenerate(image_bytes, config, client=client)

        diagram = result.diagram
        puml_text = result.puml
        total_cost = result.cost_usd
        verify_stats = None

        if verify_flag:
            verify_result = verify(
                diagram, client, max_rounds=config.verification_max_rounds, debug_dir=effective_debug_dir
            )
            diagram = verify_result.diagram
            puml_text = ir_to_puml(diagram, model_id=config.model_id)
            verify_stats = verify_result.stats
            total_cost += verify_stats.total_cost_usd

        out_path = output if output is not None else run_dir / f"{image.stem}.puml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(puml_text, encoding="utf-8")
        typer.echo(f"Wrote {out_path}")

        review_path = out_path.parent / f"{out_path.stem}.review.md"
        write_review(diagram, config.confidence_threshold, review_path)
        typer.echo(f"Wrote {review_path}")

        ir_path = out_path.parent / f"{out_path.stem}.ir.json"
        ir_path.write_text(diagram.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote {ir_path}")

        if render_format is not None:
            rendered_path = out_path.with_suffix(f".{render_format.value}")
            render_puml(puml_text, render_format.value, rendered_path)
            typer.echo(f"Rendered {rendered_path}")

        # Whitelisted fields only -- never dump `config` wholesale here,
        # since it would put OPENROUTER_API_KEY on disk in plain text if
        # a credential field were ever added to Config in the future.
        run_metadata = {
            "model_id": config.model_id,
            "cost_usd": total_cost,
            "duration_seconds": result.latency_seconds,
            "warnings": diagram.warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        run_json_path = out_path.parent / "run.json"
        run_json_path.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")
        typer.echo(f"Wrote {run_json_path}")
    except UmlRegenError as exc:
        _fail(exc)
        return

    if verbose >= 1:
        typer.echo(f"Model: {config.model_id}")
        typer.echo(f"Classes: {len(diagram.classes)}  Relationships: {len(diagram.relationships)}")
        if diagram.warnings:
            typer.echo(f"Warnings ({len(diagram.warnings)}):")
            for warning in diagram.warnings:
                typer.echo(f"  - {warning}")
    if verbose >= 2:
        typer.echo(f"Cost: ${total_cost:.4f}  Latency: {result.latency_seconds:.1f}s")
        if verify_stats is not None:
            typer.echo(
                f"Verify: {verify_stats.rounds_run} round(s), converged={verify_stats.converged}, "
                f"{verify_stats.total_calls} extra call(s), ${verify_stats.total_cost_usd:.4f}"
            )


@app.command(name="eval")
def eval_command(
    ir_dir: Path = typer.Option(Path("corpus/ir"), "--ir-dir", help="Directory of ground-truth IR JSON files."),
    img_dir: Path = typer.Option(Path("corpus/img"), "--img-dir", help="Directory of matching rendered images."),
    model: Optional[str] = typer.Option(
        None, "--model", help="Override the eval model id. Defaults to the configured eval model, not the interactive default."
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the response cache entirely."),
) -> None:
    """Score extraction against a labelled corpus (or holdout) directory."""
    config = load_config()
    model_id = model or config.eval_model_id
    client = _build_client(
        model_id,
        config.cache_dir,
        config.requests_per_minute,
        no_cache=no_cache,
        repetition_retry_attempts=config.repetition_retry_attempts,
    )

    try:
        result = run_eval_set(ir_dir, img_dir, client)
    except UmlRegenError as exc:
        _fail(exc)
        return

    for skipped in result.skipped:
        typer.echo(f"SKIP {skipped}: no rendered image found")

    if result.scored:
        aggregated = aggregate_scores([d.score for d in result.scored])
        typer.echo(format_scorecard(aggregated, title=f"Scorecard ({len(result.scored)} diagrams)"))
        typer.echo(f"\nTotal cost: ${result.total_cost_usd:.4f}")
        typer.echo(f"Total warnings: {result.total_warnings}")
        append_run_log(
            aggregated,
            model_id=model_id,
            cost_usd=result.total_cost_usd,
            latency_seconds=result.total_latency_seconds,
            warning_count=result.total_warnings,
        )
    else:
        typer.echo("No diagrams scored.")

    if result.failures:
        typer.echo()
        typer.echo(format_failure_breakdown(result.failures))
        for name, mode in result.failures:
            append_failure_log(diagram_name=name, model_id=model_id, mode=mode, message="")


@app.command()
def corpus() -> None:
    """Regenerate the corpus fixtures (.puml + rendered PNG) from corpus/ir/*.json."""
    for path in build_corpus():
        typer.echo(f"wrote {path}")


@app.command()
def doctor() -> None:
    """Check the local environment: JRE, Graphviz, plantuml.jar, API key presence, cache location."""
    config = load_config()
    try:
        tools = render_preflight()
    except UmlRegenError as exc:
        _fail(exc)
        return

    typer.echo(f"java:          {tools['java']}")
    typer.echo(f"dot:           {tools['dot']}")
    typer.echo(f"plantuml.jar:  {tools['jar']}")

    has_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    typer.echo(f"OPENROUTER_API_KEY: {'present' if has_key else 'NOT SET'}")
    typer.echo(f"cache dir:     {config.cache_dir.resolve()}")
    typer.echo("OK")


if __name__ == "__main__":
    app()
