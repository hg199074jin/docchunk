from pathlib import Path
from typing import Annotated

import typer

from docchunk.config import AppConfig
from docchunk.pipeline import batch_corpus, prepare_corpus, split_corpus

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
    typer.echo(str(split_corpus(input_path, _config_with_root(corpus_root))))


@app.command("batch")
def batch_command(
    corpus_path: ExistingPath,
) -> None:
    """Build reading batches from an existing Atomic corpus."""
    typer.echo(str(batch_corpus(corpus_path, AppConfig())))
