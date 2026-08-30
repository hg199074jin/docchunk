from pathlib import Path

import pdf_inspector

from docchunk.adapters.base import normalize_line_endings
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import (
    NativePageResult,
    PdfInspectionSummary,
    PdfInspectorBundle,
    page_number_to_index,
)


def _unique_reasons(*reason_groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in reason_groups:
        for reason in group:
            if reason and reason not in result:
                result.append(reason)
    return result


class PdfInspectorAdapter:
    """Normalize pdf-inspector's native extraction into DocChunk page models."""

    def inspect_and_extract(self, path: Path) -> PdfInspectorBundle:
        try:
            detection = pdf_inspector.detect_pdf(str(path))
        except Exception as exc:  # Rust binding errors are implementation-specific.
            raise ExternalToolError(f"pdf-inspector detection failed: {exc}") from exc

        detected_ocr_pages = {
            page_number_to_index(page_number)
            for page_number in getattr(detection, "pages_needing_ocr", [])
        }
        reasons_by_page = {
            page_number_to_index(item.page): list(item.reasons)
            for item in getattr(detection, "ocr_reasons_by_page", [])
        }
        summary = PdfInspectionSummary(
            pdf_type=str(detection.pdf_type),
            pdf_type_confidence=float(detection.confidence),
            page_count=int(detection.page_count),
            has_encoding_issues=bool(detection.has_encoding_issues),
            is_complex_layout=bool(detection.is_complex_layout),
            pages_with_tables=[int(value) for value in detection.pages_with_tables],
            pages_with_columns=[int(value) for value in detection.pages_with_columns],
        )

        try:
            extracted = pdf_inspector.extract_pages_markdown(str(path))
        except Exception:  # noqa: BLE001 — fall back to page-local extraction
            return self._extract_pages_individually(
                path,
                summary,
                detected_ocr_pages,
                reasons_by_page,
            )

        pages = [
            self._normalize_page(
                item,
                detected_ocr_pages=detected_ocr_pages,
                detected_reasons=reasons_by_page.get(int(item.page), []),
            )
            for item in extracted.pages
        ]
        return PdfInspectorBundle(summary=summary, pages=pages)

    def _extract_pages_individually(
        self,
        path: Path,
        summary: PdfInspectionSummary,
        detected_ocr_pages: set[int],
        reasons_by_page: dict[int, list[str]],
    ) -> PdfInspectorBundle:
        pages: list[NativePageResult] = []
        for page_idx in range(summary.page_count):
            try:
                result = pdf_inspector.extract_pages_markdown(
                    str(path),
                    pages=[page_idx],
                )
                if len(result.pages) != 1 or int(result.pages[0].page) != page_idx:
                    raise ValueError("single-page extraction returned an unexpected page")
            except Exception:  # noqa: BLE001 — mark only the failed page for OCR
                pages.append(
                    NativePageResult(
                        page_idx=page_idx,
                        needs_ocr=True,
                        ocr_reasons=["native_extraction_failed"],
                        extraction_failed=True,
                    )
                )
                continue

            pages.append(
                self._normalize_page(
                    result.pages[0],
                    detected_ocr_pages=detected_ocr_pages,
                    detected_reasons=reasons_by_page.get(page_idx, []),
                )
            )
        return PdfInspectorBundle(summary=summary, pages=pages)

    @staticmethod
    def _normalize_page(
        page: pdf_inspector.PageMarkdown,
        *,
        detected_ocr_pages: set[int],
        detected_reasons: list[str],
    ) -> NativePageResult:
        page_idx = int(page.page)
        needs_ocr = bool(page.needs_ocr) or page_idx in detected_ocr_pages or bool(detected_reasons)
        reasons = _unique_reasons(
            detected_reasons,
            [str(page.ocr_reason)]
            if page.ocr_reason
            else [],
        )
        if needs_ocr and not reasons:
            reasons = ["needs_ocr"]
        return NativePageResult(
            page_idx=page_idx,
            markdown=normalize_line_endings(page.markdown),
            needs_ocr=needs_ocr,
            ocr_reasons=reasons,
        )
