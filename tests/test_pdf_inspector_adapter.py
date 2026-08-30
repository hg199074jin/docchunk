from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from docchunk.adapters.pdf_inspector import PdfInspectorAdapter


def _detection() -> SimpleNamespace:
    return SimpleNamespace(
        pdf_type="mixed",
        confidence=0.7,
        page_count=3,
        pages_needing_ocr=[2],
        ocr_reasons_by_page=[SimpleNamespace(page=2, reasons=["scanned"])],
        has_encoding_issues=False,
        is_complex_layout=True,
        pages_with_tables=[3],
        pages_with_columns=[1],
    )


def test_inspector_normalizes_external_page_inventory() -> None:
    pages = [
        SimpleNamespace(page=0, markdown="native 1", needs_ocr=False, ocr_reason=None),
        SimpleNamespace(page=1, markdown="", needs_ocr=True, ocr_reason="scanned"),
        SimpleNamespace(page=2, markdown="native table", needs_ocr=False, ocr_reason=None),
    ]
    with (
        patch("docchunk.adapters.pdf_inspector.pdf_inspector.detect_pdf", return_value=_detection()),
        patch(
            "docchunk.adapters.pdf_inspector.pdf_inspector.extract_pages_markdown",
            return_value=SimpleNamespace(pages=pages),
        ),
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(Path("book.pdf"))

    assert bundle.summary.pdf_type_confidence == 0.7
    assert bundle.summary.pages_with_tables == [3]
    assert [page.page_idx for page in bundle.pages] == [0, 1, 2]
    assert bundle.pages[1].needs_ocr is True
    assert bundle.pages[1].ocr_reasons == ["scanned"]


def test_inspector_retries_each_page_when_full_extraction_fails() -> None:
    calls: list[list[int] | None] = []

    def extract(_path: str, pages: list[int] | None = None) -> SimpleNamespace:
        calls.append(pages)
        if pages is None:
            raise RuntimeError("page 2 is malformed")
        if pages == [1]:
            raise RuntimeError("page 2 is malformed")
        return SimpleNamespace(
            pages=[
                SimpleNamespace(
                    page=pages[0],
                    markdown=f"page {pages[0]}",
                    needs_ocr=False,
                    ocr_reason=None,
                )
            ]
        )

    with (
        patch("docchunk.adapters.pdf_inspector.pdf_inspector.detect_pdf", return_value=_detection()),
        patch("docchunk.adapters.pdf_inspector.pdf_inspector.extract_pages_markdown", side_effect=extract),
    ):
        bundle = PdfInspectorAdapter().inspect_and_extract(Path("book.pdf"))

    assert calls == [None, [0], [1], [2]]
    assert bundle.pages[1].extraction_failed is True
    assert bundle.pages[1].ocr_reasons == ["native_extraction_failed"]
    assert bundle.pages[0].markdown == "page 0"
