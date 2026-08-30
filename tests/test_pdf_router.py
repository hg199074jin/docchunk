import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from docchunk.adapters.base import NormalizedDocument
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import PageFragment, PdfInspectionSummary, PdfInspectorBundle


def _bundle(*pages: tuple[str, bool, list[str]]) -> PdfInspectorBundle:
    return PdfInspectorBundle(
        summary=PdfInspectionSummary(
            pdf_type="mixed",
            pdf_type_confidence=0.5,
            page_count=len(pages),
            has_encoding_issues=False,
            is_complex_layout=True,
            pages_with_tables=[3],
            pages_with_columns=[1],
        ),
        pages=[
            {
                "page_idx": index,
                "markdown": markdown,
                "needs_ocr": needs_ocr,
                "ocr_reasons": reasons,
            }
            for index, (markdown, needs_ocr, reasons) in enumerate(pages)
        ],
    )


def test_mixed_pdf_routes_only_ocr_pages_to_mineru() -> None:
    bundle = _bundle(("native one", False, []), ("", True, ["scanned"]), ("native three", False, []))
    adapter = SmartPdfAdapter()
    fake_page = Mock()
    fake_page.side_effect = lambda _path, page_idx: PageFragment(
        page_idx=page_idx,
        markdown=f"ocr {page_idx}",
        parser="mineru",
        route_reason="needs_ocr",
    )
    with patch.object(adapter.inspector, "inspect_and_extract", return_value=bundle), patch.object(
        adapter.mineru, "prepare_page", fake_page
    ):
        document = adapter.prepare(Path("audit.pdf"))

    assert fake_page.call_count == 1
    fake_page.assert_called_once_with(Path("audit.pdf"), 1)
    assert document.metadata["parser_route"] == "mixed"
    assert document.metadata["native_pages"] == 2
    assert document.metadata["mineru_pages"] == 1
    rows = [json.loads(line) for line in document.sidecars["page-routing.jsonl"].splitlines()]
    assert [row["page_number"] for row in rows] == [1, 2, 3]
    assert [row["parser"] for row in rows] == ["pdf_inspector", "mineru", "pdf_inspector"]
    assert document.text == "native one\n\nocr 1\n\nnative three"


def test_table_and_columns_do_not_force_mineru() -> None:
    bundle = _bundle(("table", False, []), ("columns", False, []))
    adapter = SmartPdfAdapter()
    with patch.object(adapter.inspector, "inspect_and_extract", return_value=bundle), patch.object(
        adapter.mineru, "prepare_page"
    ) as prepare_page:
        document = adapter.prepare(Path("layout.pdf"))

    prepare_page.assert_not_called()
    assert document.metadata["parser_route"] == "native_only"


def test_mineru_failure_does_not_fall_back_to_unreliable_native_text() -> None:
    bundle = _bundle(("", True, ["scanned"]))
    adapter = SmartPdfAdapter()
    with (
        patch.object(adapter.inspector, "inspect_and_extract", return_value=bundle),
        patch.object(
            adapter.mineru,
            "prepare_page",
            side_effect=ExternalToolError("boom"),
        ),
        pytest.raises(ExternalToolError, match="page 1.*scanned"),
    ):
        adapter.prepare(Path("scan.pdf"))


def test_inventory_mismatch_uses_whole_pdf_fallback() -> None:
    bundle = _bundle(("native", False, []))
    bundle.summary.page_count = 2
    adapter = SmartPdfAdapter()
    fallback = NormalizedDocument(
        source_path=Path("broken.pdf"),
        media_type="text/markdown",
        text="whole file",
        metadata={"adapter": "mineru"},
    )
    with patch.object(adapter.inspector, "inspect_and_extract", return_value=bundle), patch.object(
        adapter.mineru, "prepare", return_value=fallback
    ) as prepare:
        document = adapter.prepare(Path("broken.pdf"))

    prepare.assert_called_once_with(Path("broken.pdf"))
    assert document.metadata["parser_route"] == "full_mineru_fallback"
    assert document.metadata["fallback_reason"] == "page_inventory_mismatch"
