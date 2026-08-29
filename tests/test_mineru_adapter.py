import json
from pathlib import Path
from unittest.mock import patch

from docchunk.adapters.mineru import MinerUAdapter
from docchunk.provenance.mineru import (
    align_blocks_to_markdown,
    parse_content_list,
    source_pages_for_span,
)


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
