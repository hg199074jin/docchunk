"""Tests for the page assembler (routing-agnostic)."""

from pathlib import Path

import pytest

from docchunk.adapters.pdf import assemble_page_fragments, render_page_routing_jsonl
from docchunk.config import PAGE_SMART_PDF_POLICY_VERSION
from docchunk.models.pdf import (
    PageFragment,
    PdfInspectionSummary,
    PdfPageRoute,
)


def _summary(page_count: int, pdf_type: str = "mixed") -> PdfInspectionSummary:
    return PdfInspectionSummary(
        pdf_type=pdf_type,  # type: ignore[arg-type]
        pdf_type_confidence=0.7,
        page_count=page_count,
        has_encoding_issues=False,
        is_complex_layout=False,
    )


def _fragment(
    page_idx: int,
    markdown: str,
    parser: str = "pdf_inspector",
    reason: str = "native_text_safe",
) -> PageFragment:
    return PageFragment(
        page_idx=page_idx,
        markdown=markdown,
        parser=parser,  # type: ignore[arg-type]
        route_reason=reason,
        needs_ocr=parser == "mineru",
    )


def test_assembler_orders_pages_and_rebases_offsets() -> None:
    fragments = [
        _fragment(1, "第二页"),
        _fragment(0, "第一页", parser="mineru", reason="needs_ocr"),
    ]
    routes = [
        PdfPageRoute(
            page_idx=0,
            page_number=1,
            parser="mineru",
            route_reason="needs_ocr",
            needs_ocr=True,
        ),
        PdfPageRoute(
            page_idx=1,
            page_number=2,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        ),
    ]

    doc = assemble_page_fragments(Path("report.pdf"), _summary(2), fragments, routes)

    assert doc.text == "第一页\n\n第二页"
    assert [block.page_idx for block in doc.blocks] == [0, 1]
    # 后续页 block 吸收页边界 "\n\n" 前缀，保证全文被 block 完整覆盖
    assert doc.blocks[1].text.endswith("第二页")
    assert doc.blocks[1].char_start == len("第一页")
    assert doc.blocks[1].block_index == 1
    assert doc.metadata["adapter"] == "smart_pdf"
    assert doc.metadata["parser_route"] == "mixed"
    assert doc.metadata["routing"]["policy"] == PAGE_SMART_PDF_POLICY_VERSION
    assert doc.metadata["routing"]["native_pages"] == 1
    assert doc.metadata["routing"]["mineru_pages"] == 1
    assert doc.sidecars["page-routing.jsonl"].count("\n") == 2


def test_assembler_requires_full_page_coverage() -> None:
    fragments = [
        _fragment(0, "第一页"),
        _fragment(2, "第三页"),
    ]
    routes = [
        PdfPageRoute(
            page_idx=0,
            page_number=1,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        ),
        PdfPageRoute(
            page_idx=2,
            page_number=3,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        ),
    ]

    with pytest.raises(ValueError, match="cover"):
        assemble_page_fragments(Path("report.pdf"), _summary(3), fragments, routes)


def test_assembler_keeps_blank_page_numbers_stable() -> None:
    fragments = [
        _fragment(0, "第一页"),
        _fragment(1, ""),
        _fragment(2, "第三页"),
    ]
    routes = [
        PdfPageRoute(
            page_idx=page_idx,
            page_number=page_idx + 1,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        )
        for page_idx in range(3)
    ]

    doc = assemble_page_fragments(Path("report.pdf"), _summary(3), fragments, routes)

    assert doc.text == "第一页\n\n\n\n第三页"
    # 空白页不产生正文 block，但后续页码不得漂移
    assert [(block.page_idx, block.block_index) for block in doc.blocks] == [(0, 0), (2, 1)]
    third = doc.blocks[1]
    assert third.text == "\n\n\n\n第三页"
    assert doc.text[third.char_start : third.char_end] == third.text
    assert len(doc.sidecars["page-routing.jsonl"].splitlines()) == 3


def test_assembler_parser_route_values() -> None:
    native = [_fragment(0, "a"), _fragment(1, "b")]
    mineru = [
        _fragment(0, "a", parser="mineru", reason="needs_ocr"),
        _fragment(1, "b", parser="mineru", reason="needs_ocr"),
    ]
    routes_native = [
        PdfPageRoute(
            page_idx=i,
            page_number=i + 1,
            parser="pdf_inspector",
            route_reason="native_text_safe",
            needs_ocr=False,
        )
        for i in range(2)
    ]
    routes_mineru = [
        PdfPageRoute(
            page_idx=i,
            page_number=i + 1,
            parser="mineru",
            route_reason="needs_ocr",
            needs_ocr=True,
        )
        for i in range(2)
    ]

    doc_native = assemble_page_fragments(Path("x.pdf"), _summary(2), native, routes_native)
    doc_mineru = assemble_page_fragments(Path("x.pdf"), _summary(2), mineru, routes_mineru)

    assert doc_native.metadata["parser_route"] == "native_only"
    assert doc_mineru.metadata["parser_route"] == "mineru_only"


def test_render_page_routing_jsonl_contract() -> None:
    routes = [
        PdfPageRoute(
            page_idx=0,
            page_number=1,
            parser="mineru",
            route_reason="needs_ocr",
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

    rendered = render_page_routing_jsonl(routes)
    lines = rendered.splitlines()

    assert len(lines) == 2
    assert '"page_idx":0' in lines[0] and '"page_number":1' in lines[0]
    assert '"parser":"mineru"' in lines[0]
    assert '"parser":"pdf_inspector"' in lines[1]
