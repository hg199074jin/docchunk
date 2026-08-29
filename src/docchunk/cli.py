from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from docchunk.config import AppConfig
from docchunk.doctor import run_doctor
from docchunk.inspect_input import analyze_input
from docchunk.pipeline import (
    batch_corpus,
    corpus_status,
    prepare_corpus,
    rebuild_batches,
    split_corpus,
)
from docchunk.verify import verify_corpus

app = typer.Typer(
    name="docchunk",
    help="Long-document preprocessing for reliable LLM reading.",
    no_args_is_help=True,
)

console = Console()

ExistingPath = Annotated[Path, typer.Argument(exists=True, readable=True)]
ForceOption = Annotated[
    bool,
    typer.Option("--force", help="Regenerate reusable stages even if fingerprints match."),
]


@app.callback()
def _main() -> None:
    """Long-document preprocessing for reliable LLM reading."""


@app.command()
def version() -> None:
    """Show docchunk version."""
    from docchunk import __version__

    typer.echo(__version__)


def _config_with_root(corpus_root: Path | None) -> AppConfig:
    config = AppConfig()
    if corpus_root is not None:
        config = config.model_copy(update={"corpus_root": corpus_root})
    return config


@app.command()
def prepare(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
    force: ForceOption = False,
) -> None:
    """Normalize input files without creating Atomic chunks."""
    typer.echo(str(prepare_corpus(input_path, _config_with_root(corpus_root), force=force)))


@app.command()
def split(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
    force: ForceOption = False,
) -> None:
    """Prepare, split, and batch a long-document corpus."""
    result = split_corpus(
        input_path,
        _config_with_root(corpus_root),
        force=force,
    )
    report = verify_corpus(result)

    if not report.ok:
        for error in report.errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    for warning in report.warnings:
        typer.echo(f"WARNING: {warning}")

    typer.echo(str(result))


@app.command()
def verify(corpus_path: ExistingPath) -> None:
    """Verify corpus integrity, provenance, and Batch coverage."""
    report = verify_corpus(corpus_path)

    for warning in report.warnings:
        typer.echo(f"WARNING: {warning}")

    if report.ok:
        typer.echo("PASS")
        return

    for error in report.errors:
        typer.echo(f"ERROR: {error}", err=True)
    raise typer.Exit(code=1)


@app.command("batch")
def batch_command(
    corpus_path: ExistingPath,
) -> None:
    """Build reading batches from an existing Atomic corpus."""
    typer.echo(str(batch_corpus(corpus_path, AppConfig())))


@app.command()
def status(corpus_path: ExistingPath) -> None:
    """Show corpus processing state and active policies."""
    data = corpus_status(corpus_path)
    table = Table(title="docchunk corpus status")
    table.add_column("Field")
    table.add_column("Value")

    for key, value in data.items():
        table.add_row(key, str(value))

    console.print(table)


@app.command("rebuild-batches")
def rebuild_batches_command(
    corpus_path: ExistingPath,
    target_tokens: Annotated[int, typer.Option("--target-tokens")] = 24000,
    soft_min_tokens: Annotated[int, typer.Option("--soft-min-tokens")] = 16000,
    soft_max_tokens: Annotated[int, typer.Option("--soft-max-tokens")] = 32000,
    overlap_atomic_count: Annotated[
        int,
        typer.Option("--overlap-atomic-count"),
    ] = 1,
) -> None:
    """Rebuild only reading batches; never regenerate Atomic chunks."""
    result = rebuild_batches(
        corpus_path=corpus_path,
        target_tokens=target_tokens,
        soft_min_tokens=soft_min_tokens,
        soft_max_tokens=soft_max_tokens,
        overlap_atomic_count=overlap_atomic_count,
    )
    typer.echo(str(result))


@app.command()
def doctor() -> None:
    """Check the local environment: python, pandoc, mineru, tiktoken, corpus root."""
    report = run_doctor()

    for check in report.checks:
        state = "OK  " if check.ok else "FAIL"
        console.print(f"[green]{state}[/green]" if check.ok else f"[red]{state}[/red]", end=" ")
        console.print(f"{check.name}: {check.detail}")
        if not check.ok and check.fix:
            console.print(f"     fix: {check.fix}")

    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def inspect(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
) -> None:
    """Read-only analysis of an input file or directory; no corpus is created."""
    data = analyze_input(input_path, _config_with_root(corpus_root))

    for key, value in data.items():
        if value is None:
            continue
        console.print(f"{key}: {value}")
