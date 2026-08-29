from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from docchunk.config import AppConfig
from docchunk.doctor import run_doctor
from docchunk.errors import (
    DocchunkError,
    ExternalToolError,
    RebuildError,
    UnsupportedInputError,
    VerificationError,
)
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


def _emit_docchunk_error(err: DocchunkError, corpus_path: Path | None) -> None:
    """设计 §15.6：what / why / next / log_path 四要素。"""
    console.print(f"[bold red]发生了什么：[/bold red] {type(err).__name__}: {err}")

    if isinstance(err, ExternalToolError):
        console.print("[bold yellow]最可能原因：[/bold yellow] 系统里 MinerU / Pandoc 不可用或调用失败。")
        console.print(
            "[bold yellow]下一步命令：[/bold yellow]\n"
            "  1. 运行 `uv run docchunk doctor` 检查环境\n"
            "  2. 在配置中显式设置 mineru_command 为 MinerU 可执行文件绝对路径"
        )
    elif isinstance(err, VerificationError):
        console.print("[bold yellow]最可能原因：[/bold yellow] Corpus 被人为改动或原始资料变化。")
        console.print(
            "[bold yellow]下一步命令：[/bold yellow]\n"
            "  1. 运行 `uv run docchunk verify <corpus>` 查看具体错误\n"
            "  2. 必要时 `uv run docchunk split <输入> --force` 重建"
        )
    elif isinstance(err, UnsupportedInputError):
        console.print(
            "[bold yellow]下一步命令：[/bold yellow] "
            "确认输入是 .pdf/.docx/.md/.markdown/.txt 之一，或传入包含这些文件的目录。"
        )
    elif isinstance(err, RebuildError):
        console.print("[bold yellow]最可能原因：[/bold yellow] 重建 Batch 后 verify 失败。")
        console.print(
            "[bold yellow]下一步命令：[/bold yellow] 重新跑一次 `docchunk split --force`。"
        )

    if corpus_path is not None:
        log_path = corpus_path / "logs" / "processing.jsonl"
        console.print(f"[bold yellow]日志路径：[/bold yellow] {log_path}")


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


def _config_with_root(corpus_root: Path | None, verbose: bool = False) -> AppConfig:
    config = AppConfig()
    update: dict[str, object] = {}
    if corpus_root is not None:
        update["corpus_root"] = corpus_root
    if verbose:
        update["verbose"] = True
    if update:
        config = config.model_copy(update=update)
    return config


@app.command()
def prepare(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
    force: ForceOption = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Echo adapter/tool-level progress events to the console."),
    ] = False,
) -> None:
    """Normalize input files without creating Atomic chunks."""
    try:
        typer.echo(
            str(
                prepare_corpus(
                    input_path,
                    _config_with_root(corpus_root, verbose),
                    force=force,
                )
            )
        )
    except DocchunkError as err:
        _emit_docchunk_error(err, _guess_corpus_path(corpus_root, input_path))
        raise typer.Exit(code=1) from err


@app.command()
def split(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
    force: ForceOption = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Echo adapter/tool-level progress events to the console."),
    ] = False,
) -> None:
    """Prepare, split, and batch a long-document corpus."""
    try:
        result = split_corpus(
            input_path,
            _config_with_root(corpus_root, verbose),
            force=force,
        )
    except DocchunkError as err:
        _emit_docchunk_error(err, _guess_corpus_path(corpus_root, input_path))
        raise typer.Exit(code=1) from err

    report = verify_corpus(result)

    if not report.ok:
        # verify 内部的 ERROR 行由原 verify 命令输出风格保留；这里只补充四要素
        _emit_docchunk_error(VerificationError("verification failed"), result)
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
    try:
        typer.echo(str(batch_corpus(corpus_path, AppConfig())))
    except DocchunkError as err:
        _emit_docchunk_error(err, corpus_path)
        raise typer.Exit(code=1) from err


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


def _guess_corpus_path(corpus_root: Path | None, input_path: Path) -> Path | None:
    """失败早期还没生成 corpus 路径时，给 errors 输出一个 best-effort 候选。"""
    if corpus_root is None:
        corpus_root = AppConfig().corpus_root
    title = input_path.stem if input_path.is_file() else input_path.name
    return corpus_root / title


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
