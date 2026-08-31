"""Tests for SmartPdfAdapter page routing orchestration."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from docchunk.adapters.base import NormalizedDocument
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorInventoryError
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import (
    NativePageResult,
    PdfInspectionSummary,
    PdfInspectorBundle,
)


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


def _bundle(
    summary: PdfInspectionSummary,
    pages: list[NativePageResult],
) -> PdfInspectorBundle:
    return PdfInspectorBundle(summary=summary, pages=pages)


def _mineru_document(path: Path, text: str) -> NormalizedDocument:
    return NormalizedDocument(
        source_path=path,
        media_type="text/markdown",
        text=text,
        metadata={"adapter": "mineru", "backend": "hybrid-engine"},
    )


def _adapter_with(bundle: PdfInspectorBundle) -> tuple[SmartPdfAdapter, Mock]:
    mineru = Mock()
    mineru.prepare.side_effect = lambda path: _mineru_document(path, "整份 MinerU 文本")
    mineru.prepare_page.side_effect = lambda path, idx: _mineru_document(
        path, f"第{idx}页 OCR 文本"
    )
    inspector = Mock()
    inspector.inspect_and_extract.return_value = bundle
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)
    return adapter, mineru


def test_native_only_never_calls_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(3),
        [
            NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
            NativePageResult(page_idx=2, markdown="第三页", needs_ocr=False),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_not_called()
    mineru.prepare_page.assert_not_called()
    assert doc.metadata["parser_route"] == "native_only"
    assert doc.metadata["adapter"] == "smart_pdf"
    assert doc.text == "第一页\n\n第二页\n\n第三页"
    assert [block.page_idx for block in doc.blocks] == [0, 1, 2]
    assert len(doc.sidecars["page-routing.jsonl"].splitlines()) == 3


def test_mixed_audit_report_routes_only_ocr_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(5),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=2, markdown="第四页", needs_ocr=False),
            NativePageResult(page_idx=3, markdown="第五页", needs_ocr=False),
            NativePageResult(page_idx=4, markdown="第六页", needs_ocr=False),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    assert mineru.prepare_page.call_count == 2
    assert [call.args for call in mineru.prepare_page.call_args_list] == [
        (pdf, 0),
        (pdf, 1),
    ]
    mineru.prepare.assert_not_called()
    assert doc.metadata["parser_route"] == "mixed"

    rows = doc.sidecars["page-routing.jsonl"].splitlines()
    assert len(rows) == 5
    assert '"parser":"mineru"' in rows[0] and '"parser":"mineru"' in rows[1]
    assert all('"parser":"pdf_inspector"' in row for row in rows[2:])
    # 第 4 页（1-based）在 OCR 页之后必须仍是 page_idx=3
    assert doc.blocks[-1].page_idx == 4
    assert doc.text.endswith("第六页")


def test_tables_and_columns_do_not_trigger_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2, pages_with_tables=[1], pages_with_columns=[2], is_complex_layout=True),
        [
            NativePageResult(page_idx=0, markdown="表格页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="多栏页", needs_ocr=False),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    adapter.prepare(pdf)

    mineru.prepare.assert_not_called()
    mineru.prepare_page.assert_not_called()


def test_localized_encoding_issue_routes_only_flagged_page(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(3, has_encoding_issues=True),
        [
            NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
            NativePageResult(
                page_idx=2,
                markdown="",
                needs_ocr=True,
                ocr_reasons=["suspected_garbled_text"],
            ),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    assert mineru.prepare_page.call_count == 1
    assert mineru.prepare_page.call_args.args == (pdf, 2)
    assert doc.metadata["parser_route"] == "mixed"


def test_unlocalized_encoding_issue_falls_back_to_whole_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2, has_encoding_issues=True),
        [
            NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_called_once()
    mineru.prepare_page.assert_not_called()
    assert doc.metadata["parser_route"] == "full_mineru_fallback"
    assert doc.metadata["routing"]["full_fallback_reason"] == "unlocalized_encoding_issue"
    # 检测已成功：inspection 证据必须保留
    assert doc.metadata["pdf_inspection"]["has_encoding_issues"] is True
    # 清单可靠（检测成功）：逐页行仍要写入
    rows = doc.sidecars["page-routing.jsonl"].splitlines()
    assert len(rows) == 2
    assert all('"parser":"mineru"' in row for row in rows)


def test_inspector_failure_falls_back_to_whole_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    mineru = Mock()
    mineru.prepare.return_value = _mineru_document(pdf, "整份 MinerU 文本")
    inspector = Mock()
    inspector.inspect_and_extract.side_effect = RuntimeError("pdf-inspector crashed")
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_called_once()
    mineru.prepare_page.assert_not_called()
    assert doc.metadata["parser_route"] == "full_mineru_fallback"
    assert doc.metadata["routing"]["full_fallback_reason"] == "pdf_inspector_failed"
    assert "RuntimeError" in doc.metadata["routing"]["full_fallback_detail"]
    assert "pdf_inspection" not in doc.metadata


def test_inventory_mismatch_falls_back_to_whole_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    mineru = Mock()
    mineru.prepare.return_value = _mineru_document(pdf, "整份 MinerU 文本")
    inspector = Mock()
    inspector.inspect_and_extract.side_effect = PdfInspectorInventoryError(
        "page inventory mismatch: 3 reported, 2 returned"
    )
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_called_once()
    assert doc.metadata["routing"]["full_fallback_reason"] == "page_inventory_mismatch"
    # 清单不可信：不允许伪造逐页行
    assert "page-routing.jsonl" not in doc.sidecars


def test_mineru_page_failure_fails_whole_prepare(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2),
        [
            NativePageResult(page_idx=0, markdown="第一页", needs_ocr=False),
            NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
        ],
    )
    mineru = Mock()
    mineru.prepare_page.side_effect = ExternalToolError("MinerU failed: page 1 boom")
    inspector = Mock()
    inspector.inspect_and_extract.return_value = bundle
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)

    with pytest.raises(ExternalToolError):
        adapter.prepare(pdf)

    mineru.prepare.assert_not_called()


def test_pure_scanned_document_uses_single_whole_mineru_call(tmp_path: Path) -> None:
    """方案 A：纯扫描 PDF 整份一次 MinerU，不做逐页调用。"""
    pdf = tmp_path / "scanned.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(3, pdf_type="scanned"),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=2, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
        ],
    )
    adapter, mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_called_once_with(pdf)
    mineru.prepare_page.assert_not_called()
    assert doc.metadata["adapter"] == "smart_pdf"
    assert doc.metadata["parser_route"] == "mineru_only"
    assert doc.metadata["pdf_inspection"]["pdf_type"] == "scanned"
    routing = doc.metadata["routing"]
    assert routing["policy"] == "page_smart_v1"
    assert routing["native_pages"] == 0
    assert routing["mineru_pages"] == 3
    assert routing["mineru_invocation"] == "whole_document"
    assert doc.text == "整份 MinerU 文本"
    assert doc.media_type == "application/pdf"
    rows = doc.sidecars["page-routing.jsonl"].splitlines()
    assert len(rows) == 3
    assert all('"parser":"mineru"' in row for row in rows)


def test_mixed_path_marks_per_page_mineru_invocation(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    bundle = _bundle(
        _summary(2),
        [
            NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
            NativePageResult(page_idx=1, markdown="第二页", needs_ocr=False),
        ],
    )
    adapter, _mineru = _adapter_with(bundle)

    doc = adapter.prepare(pdf)

    assert doc.metadata["routing"]["mineru_invocation"] == "per_page"
