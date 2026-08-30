from pathlib import Path

from docchunk.adapters.base import NormalizedBlock
from docchunk.adapters.pdf import assemble_page_fragments
from docchunk.models.pdf import PageFragment, PdfPageRoute


def test_assembler_preserves_page_order_and_recomputes_offsets() -> None:
    fragments = [
        PageFragment(
            page_idx=1,
            markdown="第二页",
            parser="pdf_inspector",
            route_reason="native_text_safe",
        ),
        PageFragment(
            page_idx=0,
            markdown="第一页",
            blocks=[
                NormalizedBlock(
                    block_index=9,
                    char_start=0,
                    char_end=3,
                    text="第一页",
                    page_idx=0,
                )
            ],
            parser="mineru",
            route_reason="scanned",
        ),
    ]
    routes = [
        PdfPageRoute(
            page_idx=0,
            page_number=1,
            parser="mineru",
            route_reason="scanned",
            needs_ocr=True,
            ocr_reasons=["scanned"],
        ),
        PdfPageRoute(
            page_idx=1,
            page_number=2,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        ),
    ]

    document = assemble_page_fragments(
        Path("book.pdf"), fragments, metadata={}, routes=routes
    )

    assert document.text == "第一页\n\n第二页"
    assert [(block.page_idx, block.char_start, block.char_end) for block in document.blocks] == [
        (0, 0, 3),
        (1, 5, 8),
    ]
    assert document.metadata["parser_route"] == "mixed"
    assert document.sidecars["page-routing.jsonl"].count("\n") == 2


def test_assembler_rejects_missing_page_instead_of_guessing() -> None:
    fragment = PageFragment(
        page_idx=2,
        markdown="third",
        parser="pdf_inspector",
        route_reason="native_text_safe",
    )
    try:
        assemble_page_fragments(Path("book.pdf"), [fragment], metadata={}, routes=[])
    except ValueError as exc:
        assert "cover" in str(exc)
    else:
        raise AssertionError("missing page must fail")
