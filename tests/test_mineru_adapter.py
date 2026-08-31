import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from docchunk.adapters.mineru import MinerUAdapter
from docchunk.provenance.mineru import (
    align_blocks_to_markdown,
    parse_content_list,
)
from docchunk.provenance.pages import source_pages_for_span


def _fixture_blocks():
    path = Path("tests/fixtures/mineru-content-list.json")
    content = json.loads(path.read_text(encoding="utf-8"))
    return parse_content_list(content)


def test_content_list_keeps_mineru_zero_based_page_index() -> None:
    blocks = _fixture_blocks()

    assert blocks[0].page_idx == 0
    assert blocks[2].page_idx == 1
    assert blocks[0].heading_level == 1
    assert blocks[2].heading_level == 2


def test_blocks_are_aligned_to_real_markdown_offsets() -> None:
    markdown = Path("tests/fixtures/mineru-normalized.md").read_text(encoding="utf-8")
    blocks = align_blocks_to_markdown(markdown, _fixture_blocks())

    first_body = blocks[1]
    assert markdown[first_body.char_start:first_body.char_end] == "这是第一页正文。"


def test_atomic_span_maps_to_human_page_numbers() -> None:
    markdown = Path("tests/fixtures/mineru-normalized.md").read_text(encoding="utf-8")
    blocks = align_blocks_to_markdown(markdown, _fixture_blocks())

    second_start = markdown.index("第二节")
    page_start, page_end = source_pages_for_span(
        blocks,
        char_start=second_start,
        char_end=len(markdown),
    )

    assert (page_start, page_end) == (2, 2)


def test_mineru_adapter_uses_generated_markdown_and_content_list(tmp_path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")

    output = tmp_path / "mineru-output"
    output.mkdir()
    (output / "book.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    (output / "book_content_list.json").write_text(
        '[{"type":"text","text":"标题","text_level":1,"page_idx":0},'
        '{"type":"text","text":"正文。","page_idx":0}]',
        encoding="utf-8",
    )

    with patch.object(MinerUAdapter, "_run_mineru", return_value=output):
        doc = MinerUAdapter().prepare(pdf)

    assert doc.text.startswith("# 标题")
    assert doc.blocks[0].page_idx == 0
    assert doc.blocks[0].char_start == doc.text.index("标题")
    assert doc.metadata["adapter"] == "mineru"
    assert doc.metadata["unaligned_blocks"] == 0


def test_mineru_adapter_handles_glob_metacharacters_in_filename(tmp_path) -> None:
    """文件名含 [ ] ( ) 等 glob 元字符时，输出发现必须按字面名匹配（v1.0.2 回归）。"""
    pdf = tmp_path / "书 [第2版] (扫描) 注?释.pdf"
    pdf.write_bytes(b"%PDF-fake")
    stem = pdf.stem

    output = tmp_path / "mineru-output"
    nested = output / stem / "auto"
    nested.mkdir(parents=True)
    (nested / f"{stem}.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    (nested / f"{stem}_content_list.json").write_text(
        '[{"type":"text","text":"标题","text_level":1,"page_idx":0},'
        '{"type":"text","text":"正文。","page_idx":0}]',
        encoding="utf-8",
    )

    with patch.object(MinerUAdapter, "_run_mineru", return_value=output):
        doc = MinerUAdapter().prepare(pdf)

    assert doc.text.startswith("# 标题")
    assert doc.blocks[0].page_idx == 0
    assert doc.blocks[0].char_start == doc.text.index("标题")
    assert doc.metadata["unaligned_blocks"] == 0


def test_run_mineru_passes_page_range_to_cli(tmp_path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_output = tmp_path / "fake-output"
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")

    with (
        patch("docchunk.adapters.mineru.subprocess.run", return_value=completed) as run,
        patch(
            "docchunk.adapters.mineru.tempfile.mkdtemp", return_value=str(fake_output)
        ),
    ):
        MinerUAdapter()._run_mineru(pdf, start_page=37, end_page=37)

    argv = run.call_args.args[0]
    assert argv[argv.index("--start") + 1] == "37"
    assert argv[argv.index("--end") + 1] == "37"


def test_run_mineru_omits_range_for_whole_document(tmp_path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_output = tmp_path / "fake-output"
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")

    with (
        patch("docchunk.adapters.mineru.subprocess.run", return_value=completed) as run,
        patch(
            "docchunk.adapters.mineru.tempfile.mkdtemp", return_value=str(fake_output)
        ),
    ):
        MinerUAdapter()._run_mineru(pdf)

    argv = run.call_args.args[0]
    assert "--start" not in argv
    assert "--end" not in argv


def test_run_mineru_cleans_temp_dir_on_failure(tmp_path) -> None:
    """失败分支也必须清理临时目录（v1.0.2 C3 修复的完整版）。"""
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")

    real_mkdtemp = tempfile.mkdtemp
    created: list[Path] = []

    def tracking_mkdtemp(*args: object, **kwargs: object) -> str:
        path = Path(real_mkdtemp(prefix="docchunk-mineru-test-"))  # type: ignore[arg-type]
        created.append(path)
        return str(path)

    completed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    with (
        patch("docchunk.adapters.mineru.subprocess.run", return_value=completed),
        patch("docchunk.adapters.mineru.tempfile.mkdtemp", side_effect=tracking_mkdtemp),
        pytest.raises(Exception, match="MinerU failed"),
    ):
        MinerUAdapter()._run_mineru(pdf)

    assert len(created) == 1
    assert not created[0].exists(), "failed MinerU temp dir must be cleaned up"


def test_prepare_page_rejects_negative_page(tmp_path) -> None:
    with pytest.raises(ValueError, match="page_idx"):
        MinerUAdapter().prepare_page(tmp_path / "book.pdf", -1)


def test_prepare_page_forces_original_page_index(tmp_path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")

    output = tmp_path / "mineru-output"
    output.mkdir()
    (output / "book.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    # MinerU 对范围输出可能给 page_idx=0；DocChunk 必须强制改写为原 PDF 页码
    (output / "book_content_list.json").write_text(
        '[{"type":"text","text":"标题","text_level":1,"page_idx":0},'
        '{"type":"text","text":"正文。","page_idx":0}]',
        encoding="utf-8",
    )

    with patch.object(MinerUAdapter, "_run_mineru", return_value=output) as run:
        doc = MinerUAdapter().prepare_page(pdf, 37)

    run.assert_called_once_with(pdf, start_page=37, end_page=37)
    assert [block.page_idx for block in doc.blocks] == [37, 37]
    assert doc.metadata["page_mode"] is True
    assert doc.metadata["source_page_idx"] == 37
    assert doc.text.startswith("# 标题")
