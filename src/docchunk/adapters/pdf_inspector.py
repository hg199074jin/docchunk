"""Boundary adapter around the pdf-inspector Python API.

Conventions verified against pdf-inspector 1.17.0:

- ``PageMarkdown.page`` is 0-based and maps directly to DocChunk ``page_idx``;
- ``pages_needing_ocr`` / ``ocr_reasons_by_page[].page`` are 1-based and are
  shifted here — never in business code;
- ``PagesExtractionResult`` carries no ``page_count``; inventory validation
  therefore uses ``detect_pdf().page_count``;
- extraction-time ``needs_ocr`` is the SOLE per-page routing authority.
  Detection-side per-page flags are recorded as diagnostics only: real-world
  evidence (2026-08-31) shows detection can flag perfectly readable text
  pages as needing OCR, and routing on those flags would send good native
  text through OCR against the core principle (design §2/§10).

This module never calls MinerU and never uses pdf-inspector OCR features.
"""

from pathlib import Path
from typing import Any

import pdf_inspector

from docchunk.models.pdf import (
    NativePageResult,
    PdfInspectionSummary,
    PdfInspectorBundle,
    page_number_to_index,
)

_PDF_TYPES = {"text_based", "scanned", "image_based", "mixed"}


class PdfInspectorInventoryError(RuntimeError):
    """Raised when the page inventory cannot be trusted for page routing."""


class PdfInspectorAdapter:
    def inspect_and_extract(self, path: Path) -> PdfInspectorBundle:
        detected = pdf_inspector.detect_pdf(str(path))
        summary = self._build_summary(detected)
        try:
            extracted = pdf_inspector.extract_pages_markdown(str(path))
            pages = self._normalize_pages(extracted.pages)
        except Exception:  # noqa: BLE001 — 外部库边界：失败形态不可枚举，逐页隔离重试兜底
            pages = self._extract_pages_individually(path, summary.page_count)
        self._validate_inventory(summary.page_count, pages)
        pages = self._apply_detected_ocr_reasons(detected, pages)
        return PdfInspectorBundle(summary=summary, pages=pages)

    def _build_summary(self, detected: Any) -> PdfInspectionSummary:
        pdf_type = getattr(detected, "pdf_type", None)
        if pdf_type not in _PDF_TYPES:
            raise PdfInspectorInventoryError(f"unrecognized pdf_type: {pdf_type!r}")
        page_count = getattr(detected, "page_count", None)
        if not isinstance(page_count, int) or page_count <= 0:
            raise PdfInspectorInventoryError(f"unreliable page_count: {page_count!r}")
        return PdfInspectionSummary(
            pdf_type=pdf_type,
            pdf_type_confidence=float(getattr(detected, "confidence", 0.0)),
            page_count=page_count,
            has_encoding_issues=bool(getattr(detected, "has_encoding_issues", False)),
            is_complex_layout=bool(getattr(detected, "is_complex_layout", False)),
            # 用户可读 1-based metadata，保持库的原始约定
            pages_with_tables=[int(p) for p in getattr(detected, "pages_with_tables", [])],
            pages_with_columns=[
                int(p) for p in getattr(detected, "pages_with_columns", [])
            ],
        )

    def _normalize_pages(self, pages: list[Any]) -> list[NativePageResult]:
        normalized = [
            NativePageResult(
                page_idx=int(page.page),
                markdown=page.markdown or "",
                needs_ocr=bool(page.needs_ocr),
                # 提取期是单数 ocr_reason；统一成复数列表
                ocr_reasons=[page.ocr_reason] if page.ocr_reason else [],
            )
            for page in pages
        ]
        normalized.sort(key=lambda page: page.page_idx)
        return normalized

    def _extract_pages_individually(
        self,
        path: Path,
        page_count: int,
    ) -> list[NativePageResult]:
        pages: list[NativePageResult] = []
        for page_idx in range(page_count):
            try:
                extracted = pdf_inspector.extract_pages_markdown(
                    str(path),
                    pages=[page_idx],
                )
                page_results = self._normalize_pages(extracted.pages)
                match = next(
                    (item for item in page_results if item.page_idx == page_idx),
                    None,
                )
                pages.append(match if match is not None else _failed_page(page_idx))
            except Exception:  # noqa: BLE001 — 单页失败只影响该页，见设计 §25
                pages.append(_failed_page(page_idx))
        return pages

    def _validate_inventory(
        self,
        page_count: int,
        pages: list[NativePageResult],
    ) -> None:
        actual = [page.page_idx for page in pages]
        if actual != list(range(page_count)):
            raise PdfInspectorInventoryError(
                f"page inventory mismatch: detect_pdf reported {page_count} pages, "
                f"extraction returned {len(pages)}"
            )

    def _apply_detected_ocr_reasons(
        self,
        detected: Any,
        pages: list[NativePageResult],
    ) -> list[NativePageResult]:
        """Merge detection-side reasons as diagnostics; never flip ``needs_ocr``.

        提取期 ``needs_ocr`` 是唯一路由权威：实测（2026-08-31）detect 会把
        完全可读的文字页误标为需 OCR，依据 detect 强制路由会违反 §2 核心原则。
        """
        # detect 级页码是 1-based：在此统一 −1，业务代码不出现裸转换
        localized: dict[int, list[str]] = {}
        for entry in getattr(detected, "ocr_reasons_by_page", []) or []:
            page_number = int(entry.page)
            if page_number < 1:
                continue
            localized.setdefault(page_number_to_index(page_number), []).extend(
                entry.reasons
            )
        for page_number in getattr(detected, "pages_needing_ocr", []) or []:
            number = int(page_number)
            if number < 1:
                continue
            localized.setdefault(page_number_to_index(number), [])

        updated: list[NativePageResult] = []
        for page in pages:
            reasons = list(page.ocr_reasons)
            for reason in localized.get(page.page_idx, []):
                if reason and reason not in reasons:
                    reasons.append(reason)
            changed = reasons != page.ocr_reasons
            updated.append(
                page.model_copy(update={"ocr_reasons": reasons}) if changed else page
            )
        return updated


def _failed_page(page_idx: int) -> NativePageResult:
    return NativePageResult(
        page_idx=page_idx,
        markdown="",
        needs_ocr=True,
        ocr_reasons=["native_extraction_failed"],
        extraction_failed=True,
    )
