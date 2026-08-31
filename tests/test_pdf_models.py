"""Tests for PDF routing internal models and page number helpers."""

import pytest
from pydantic import ValidationError

from docchunk.models.pdf import (
    NativePageResult,
    PageFragment,
    PdfInspectionSummary,
    PdfInspectorBundle,
    PdfPageRoute,
    page_index_to_number,
    page_number_to_index,
)


def test_page_number_helpers_have_one_authoritative_conversion() -> None:
    assert page_index_to_number(0) == 1
    assert page_index_to_number(99) == 100
    assert page_number_to_index(1) == 0
    assert page_number_to_index(100) == 99


@pytest.mark.parametrize("bad", [-1, -2])
def test_page_index_rejects_negative_values(bad: int) -> None:
    with pytest.raises(ValueError):
        page_index_to_number(bad)


@pytest.mark.parametrize("bad", [0, -1])
def test_page_number_rejects_non_positive_values(bad: int) -> None:
    with pytest.raises(ValueError):
        page_number_to_index(bad)


def test_pdf_route_keeps_internal_and_user_page_numbers_consistent() -> None:
    route = PdfPageRoute(
        page_idx=2,
        page_number=3,
        parser="mineru",
        route_reason="needs_ocr",
        needs_ocr=True,
        ocr_reasons=["scanned"],
    )
    assert route.page_number == route.page_idx + 1


def test_pdf_route_rejects_inconsistent_page_number() -> None:
    with pytest.raises(ValidationError):
        PdfPageRoute(
            page_idx=2,
            page_number=4,
            parser="mineru",
            route_reason="needs_ocr",
            needs_ocr=True,
        )


def test_inspection_summary_defaults_match_contract() -> None:
    summary = PdfInspectionSummary(
        pdf_type="mixed",
        pdf_type_confidence=0.7,
        page_count=100,
        has_encoding_issues=False,
        is_complex_layout=True,
        pages_with_tables=[5, 6, 20],
        pages_with_columns=[],
    )
    assert summary.engine == "pdf-inspector"
    # table/column page lists stay user-facing 1-based metadata
    assert summary.pages_with_tables == [5, 6, 20]
    assert summary.pages_with_columns == []


def test_inspection_summary_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        PdfInspectionSummary(
            pdf_type="text_based",
            pdf_type_confidence=1.5,
            page_count=1,
            has_encoding_issues=False,
            is_complex_layout=False,
        )


def test_inspection_summary_rejects_non_positive_page_count() -> None:
    with pytest.raises(ValidationError):
        PdfInspectionSummary(
            pdf_type="text_based",
            pdf_type_confidence=0.9,
            page_count=0,
            has_encoding_issues=False,
            is_complex_layout=False,
        )


def test_native_page_result_defaults() -> None:
    page = NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False)
    assert page.ocr_reasons == []
    assert page.extraction_failed is False


def test_native_page_result_rejects_negative_page_idx() -> None:
    with pytest.raises(ValidationError):
        NativePageResult(page_idx=-1, markdown="", needs_ocr=True)


def test_page_fragment_defaults() -> None:
    fragment = PageFragment(
        page_idx=37,
        markdown="……",
        parser="mineru",
        route_reason="needs_ocr",
        needs_ocr=True,
    )
    assert fragment.blocks == []


def test_bundle_groups_summary_and_pages() -> None:
    summary = PdfInspectionSummary(
        pdf_type="text_based",
        pdf_type_confidence=0.9,
        page_count=2,
        has_encoding_issues=False,
        is_complex_layout=False,
    )
    pages = [
        NativePageResult(page_idx=0, markdown="a", needs_ocr=False),
        NativePageResult(page_idx=1, markdown="b", needs_ocr=False),
    ]
    bundle = PdfInspectorBundle(summary=summary, pages=pages)
    assert bundle.summary.page_count == 2
    assert [page.page_idx for page in bundle.pages] == [0, 1]
