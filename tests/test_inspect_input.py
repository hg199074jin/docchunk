"""Tests for PDF preflight in ``docchunk inspect`` and page range display."""

from pathlib import Path
from unittest.mock import patch

from docchunk.adapters.pdf_inspector import PdfInspectorAdapter
from docchunk.config import AppConfig
from docchunk.inspect_input import analyze_input, compact_page_ranges
from docchunk.models.pdf import NativePageResult, PdfInspectionSummary, PdfInspectorBundle


def _summary(page_count: int, **overrides: object) -> PdfInspectionSummary:
    values: dict[str, object] = {
        "pdf_type": "mixed",
        "pdf_type_confidence": 0.7,
        "page_count": page_count,
        "has_encoding_issues": False,
        "is_complex_layout": False,
        "pages_with_tables": [],
        "pages_with_columns": [],
    }
    values.update(overrides)
    return PdfInspectionSummary(**values)  # type: ignore[arg-type]


def _bundle(summary: PdfInspectionSummary, pages: list[NativePageResult]) -> PdfInspectorBundle:
    return PdfInspectorBundle(summary=summary, pages=pages)


def test_compact_page_ranges_formats_contiguous_runs() -> None:
    assert compact_page_ranges([1, 2, 3, 21, 84, 85]) == "1-3, 21, 84-85"
    assert compact_page_ranges([5]) == "5"
    assert compact_page_ranges([]) == ""
    assert compact_page_ranges([1, 2, 3, 4, 5, 6, 7]) == "1-7"


def test_analyze_pdf_preflight_reports_planned_routing_without_mineru(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(5, pages_with_tables=[3]),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=2, markdown="第三页", needs_ocr=False),
            NativePageResult(page_idx=3, markdown="第四页", needs_ocr=False),
            NativePageResult(page_idx=4, markdown="第五页", needs_ocr=False),
        ],
    )

    with (
        patch.object(PdfInspectorAdapter, "inspect_and_extract", return_value=bundle),
        patch("docchunk.adapters.mineru.MinerUAdapter.prepare") as prepare,
        patch("docchunk.adapters.mineru.MinerUAdapter.prepare_page") as prepare_page,
    ):
        data = analyze_input(pdf, AppConfig(corpus_root=tmp_path / "corpora"))

    prepare.assert_not_called()
    prepare_page.assert_not_called()

    entry = data["pdf_files"][0]  # type: ignore[index]
    assert entry["file"] == "report.pdf"
    assert entry["pdf_type"] == "mixed"
    assert entry["page_count"] == 5
    assert entry["planned_native_pages"] == 3
    assert entry["planned_mineru_pages"] == 2
    # 用户输出 1-based
    assert entry["ocr_pages"] == [1, 2]
    assert entry["pages_with_tables"] == [3]
    assert entry["route_policy"] == "page_smart_v1"
    assert entry["mineru_invocation"] == "per_page"


def test_analyze_pdf_pure_scanned_plans_whole_document_call(tmp_path: Path) -> None:
    pdf = tmp_path / "scanned.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2, pdf_type="scanned"),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
        ],
    )

    with patch.object(PdfInspectorAdapter, "inspect_and_extract", return_value=bundle):
        data = analyze_input(pdf, AppConfig(corpus_root=tmp_path / "corpora"))

    entry = data["pdf_files"][0]  # type: ignore[index]
    assert entry["planned_mineru_pages"] == 2
    assert entry["planned_native_pages"] == 0
    assert entry["mineru_invocation"] == "whole_document"


def test_analyze_pdf_unlocalized_encoding_plans_full_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "weird.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2, has_encoding_issues=True),
        [
            NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
        ],
    )

    with patch.object(PdfInspectorAdapter, "inspect_and_extract", return_value=bundle):
        data = analyze_input(pdf, AppConfig(corpus_root=tmp_path / "corpora"))

    entry = data["pdf_files"][0]  # type: ignore[index]
    assert entry["planned_mineru_pages"] == 2
    assert entry["full_fallback_reason"] == "unlocalized_encoding_issue"
    assert entry["mineru_invocation"] == "whole_document"


def test_analyze_pdf_inspector_failure_plans_full_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-fake")

    with (
        patch.object(
            PdfInspectorAdapter,
            "inspect_and_extract",
            side_effect=RuntimeError("boom"),
        ),
        patch("docchunk.adapters.mineru.MinerUAdapter.prepare") as prepare,
        patch("docchunk.adapters.mineru.MinerUAdapter.prepare_page") as prepare_page,
    ):
        data = analyze_input(pdf, AppConfig(corpus_root=tmp_path / "corpora"))

    prepare.assert_not_called()
    prepare_page.assert_not_called()

    entry = data["pdf_files"][0]  # type: ignore[index]
    assert entry["full_fallback_reason"] == "pdf_inspector_failed"
    assert "RuntimeError" in str(entry["full_fallback_detail"])


def test_analyze_directory_aggregates_pdf_planned_totals(tmp_path: Path) -> None:
    directory = tmp_path / "docs"
    directory.mkdir()
    (directory / "a.pdf").write_bytes(b"%PDF-fake")
    (directory / "b.txt").write_text("纯文本。", encoding="utf-8")
    bundle = _bundle(
        _summary(2),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
        ],
    )

    with patch.object(PdfInspectorAdapter, "inspect_and_extract", return_value=bundle):
        data = analyze_input(directory, AppConfig(corpus_root=tmp_path / "corpora"))

    assert data["planned_native_pages_total"] == 1
    assert data["planned_mineru_pages_total"] == 1
    assert len(data["pdf_files"]) == 1  # type: ignore[arg-type]
