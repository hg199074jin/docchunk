import typer

app = typer.Typer(
    name="docchunk",
    help="Long-document preprocessing for reliable LLM reading.",
    no_args_is_help=True,
)


@app.callback()
def _main() -> None:
    """Long-document preprocessing for reliable LLM reading."""


@app.command()
def version() -> None:
    """Show docchunk version."""
    from docchunk import __version__

    typer.echo(__version__)
