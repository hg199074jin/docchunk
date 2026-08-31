from pathlib import Path

import pytest

from docchunk.adapters.directory import discover_inputs
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.errors import UnsupportedInputError
from docchunk.inspect_input import choose_adapter


def test_directory_uses_natural_numeric_order(tmp_path: Path) -> None:
    for name in ["10-第十课.md", "2-第二课.md", "1-第一课.md", "ignore.jpg"]:
        (tmp_path / name).write_text("x", encoding="utf-8")

    files = discover_inputs(tmp_path)

    assert [path.name for path in files] == [
        "1-第一课.md",
        "2-第二课.md",
        "10-第十课.md",
    ]


def test_choose_markdown_adapter() -> None:
    assert isinstance(choose_adapter(Path("a.md")), MarkdownAdapter)


def test_pdf_uses_smart_pdf_adapter(tmp_path: Path) -> None:
    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-fake")

    adapter = choose_adapter(path)

    assert isinstance(adapter, SmartPdfAdapter)


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedInputError):
        choose_adapter(Path("a.jpg"))
