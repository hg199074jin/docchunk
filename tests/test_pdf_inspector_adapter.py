"""Tests for the pdf-inspector boundary adapter."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from docchunk.adapters.pdf_inspector import (
    PdfInspectorAdapter,
    PdfInspectorInventoryError,
)


def _detected(page_count: int = 3, **overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "pdf_type": "mixed",
        "confidence": 0.7,
        "page_count": page_count,
        "has_encoding_issues": False,
        "is_complex_layout": True,
        "pages_with_tables": [2],
        "pages_with_columns": [],
        "pages_needing_ocr": [],
        "ocr_reasons_by_page": [],
        "title": None,
        "processing_time_ms": 12,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _extracted(pages: list[SimpleNamespace], **overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "pages": pages,
        "pages_with_tables": [2],
        "pages_with_columns": [],
        "pages_needing_ocr": [],
        "ocr_reasons_by_page": [],
        "is_complex": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _page(page: int, markdown: str, needs_ocr: bool, reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(page=page, markdown=markdown, needs_ocr=needs_ocr, ocr_reason=reason)


def test_inspector_normalizes_page_results_to_zero_based(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(pages_needing_ocr=[1], ocr_reasons_by_page=[
        SimpleNamespace(page=1, reasons=["scanned"])
    ])
    extracted = _extracted(
        pages=[
            _page(0, "", True, "scanned"),
            _page(1, "第二页", False, None),
            _page(2, "第三页", False, None),
        ],
        pages_needing_ocr=[1],
        ocr_reasons_by_page=[SimpleNamespace(page=1, reasons=["scanned"])],
    )

    with patch("pdf_inspector.detect_pdf", return_value=detected), patch(
        "pdf_inspector.extract_pages_markdown", return_value=extracted
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(pdf)

    assert bundle.summary.page_count == 3
    assert bundle.summary.pdf_type == "mixed"
    assert bundle.summary.pdf_type_confidence == pytest.approx(0.7)
    assert bundle.summary.is_complex_layout is True
    # table/column lists stay user-facing 1-based
    assert bundle.summary.pages_with_tables == [2]
    assert bundle.pages[0].page_idx == 0
    assert bundle.pages[0].needs_ocr is True
    # singular extract reason + plural detect reason merged, deduped
    assert bundle.pages[0].ocr_reasons == ["scanned"]
    assert bundle.pages[1].page_idx == 1
    assert bundle.pages[1].needs_ocr is False
    assert bundle.pages[2].page_idx == 2


def test_inspector_records_detect_reasons_without_flipping_needs_ocr(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(page_count=2)
    extracted = _extracted(
        pages=[
            _page(0, "第一页", False, None),
            _page(1, "第二页", False, None),
        ],
    )
    # 实测（2026-08-31）：detect 可能把可读文字页也误标为需 OCR。
    # 提取期 needs_ocr 是唯一路由权威，detect 信息只作诊断记录。
    detected.ocr_reasons_by_page = [SimpleNamespace(page=2, reasons=["empty_page"])]
    detected.pages_needing_ocr = [2]
    extracted.ocr_reasons_by_page = [SimpleNamespace(page=2, reasons=["empty_page"])]

    with patch("pdf_inspector.detect_pdf", return_value=detected), patch(
        "pdf_inspector.extract_pages_markdown", return_value=extracted
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(pdf)

    assert bundle.pages[0].needs_ocr is False
    assert bundle.pages[1].needs_ocr is False
    assert bundle.pages[1].ocr_reasons == ["empty_page"]


def test_inspector_raises_on_page_inventory_mismatch(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(page_count=3)
    extracted = _extracted(
        pages=[
            _page(0, "第一页", False, None),
            _page(1, "第二页", False, None),
        ]
    )

    with (
        patch("pdf_inspector.detect_pdf", return_value=detected),
        patch("pdf_inspector.extract_pages_markdown", return_value=extracted),
        pytest.raises(PdfInspectorInventoryError),
    ):
        PdfInspectorAdapter().inspect_and_extract(pdf)


def test_inspector_retries_pages_individually_after_full_failure(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(page_count=3)
    good = _extracted(pages=[_page(0, "第一页", False, None)])

    calls: list[object] = []

    def extract(path: object, pages: list[int] | None = None) -> SimpleNamespace:
        calls.append(pages)
        if pages is None:
            raise RuntimeError("layout explosion")
        if pages == [0]:
            return good
        raise RuntimeError(f"page render error on {pages}")

    with patch("pdf_inspector.detect_pdf", return_value=detected), patch(
        "pdf_inspector.extract_pages_markdown", side_effect=extract
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(pdf)

    assert calls[0] is None
    assert bundle.pages[0].page_idx == 0
    assert bundle.pages[0].needs_ocr is False

    failed = [page for page in bundle.pages if page.extraction_failed]
    assert [page.page_idx for page in failed] == [1, 2]
    for page in failed:
        assert page.markdown == ""
        assert page.needs_ocr is True
        assert page.ocr_reasons == ["native_extraction_failed"]


def test_inspector_wraps_singular_ocr_reason(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(page_count=1)
    extracted = _extracted(pages=[_page(0, "正文", False, "suspected_garbled_text")])

    with patch("pdf_inspector.detect_pdf", return_value=detected), patch(
        "pdf_inspector.extract_pages_markdown", return_value=extracted
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(pdf)

    assert bundle.pages[0].ocr_reasons == ["suspected_garbled_text"]


def test_inspector_normalizes_detect_page_lists(tmp_path: Path) -> None:
    """detect 级 1-based 清单必须能匹配 0-based 页结果（-1 边界）。"""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")

    detected = _detected(
        has_encoding_issues=True,
        pages_needing_ocr=[3],
        ocr_reasons_by_page=[SimpleNamespace(page=3, reasons=["suspected_garbled_text"])],
    )
    extracted = _extracted(
        pages=[
            _page(0, "第一页", False, None),
            _page(1, "第二页", False, None),
            _page(2, "第三页", False, None),
        ]
    )

    with patch("pdf_inspector.detect_pdf", return_value=detected), patch(
        "pdf_inspector.extract_pages_markdown", return_value=extracted
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(pdf)

    assert bundle.summary.has_encoding_issues is True
    # detect 的第 3 页（1-based）= 内部 page_idx 2
    assert bundle.pages[2].ocr_reasons == ["suspected_garbled_text"]
