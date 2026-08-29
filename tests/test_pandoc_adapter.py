from pathlib import Path
from unittest.mock import patch

import pytest

from docchunk.adapters.pandoc import PandocAdapter
from docchunk.errors import ExternalToolError


def test_pandoc_adapter_reads_stdout_markdown(tmp_path: Path) -> None:
    source = tmp_path / "book.docx"
    source.write_bytes(b"fake-docx")

    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "# 标题\n\n正文。\n"
        run.return_value.stderr = ""

        doc = PandocAdapter().prepare(source)

    assert doc.text == "# 标题\n\n正文。\n"
    assert doc.metadata["adapter"] == "pandoc"


def test_pandoc_failure_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "book.docx"
    source.write_bytes(b"fake-docx")

    with patch("subprocess.run") as run:
        run.return_value.returncode = 2
        run.return_value.stdout = ""
        run.return_value.stderr = "bad docx"

        with pytest.raises(ExternalToolError, match="Pandoc failed"):
            PandocAdapter().prepare(source)
