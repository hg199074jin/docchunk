from pathlib import Path
from typing import Annotated

import typer

from docchunk.config import AppConfig
from docchunk.pipeline import batch_corpus, prepare_corpus, split_corpus
from docchunk.verify import verify_corpus

app = typer.Typer(
    name="docchunk",
    help="Long-document preprocessing for reliable LLM reading.",
    no_args_is_help=True,
)

ExistingPath = Annotated[Path, typer.Argument(exists=True, readable=True)]


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
) -> None:
    """Normalize input files without creating Atomic chunks."""
    typer.echo(str(prepare_corpus(input_path, _config_with_root(corpus_root))))


@app.command()
def split(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
) -> None:
    """Prepare, split, and batch a long-document corpus."""
    result = split_corpus(input_path, _config_with_root(corpus_root))
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
