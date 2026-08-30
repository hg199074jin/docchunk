from typing import Literal

from pydantic import BaseModel, Field

from docchunk.adapters.base import NormalizedBlock

PAGE_SMART_PDF_POLICY_VERSION = "page_smart_v1"


def page_index_to_number(page_idx: int) -> int:
    if page_idx < 0:
        raise ValueError("page_idx must be >= 0")
    return page_idx + 1


def page_number_to_index(page_number: int) -> int:
    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    return page_number - 1


def format_page_ranges(page_numbers: list[int]) -> str:
    """Render sorted 1-based page numbers compactly for human-facing output."""
    if not page_numbers:
        return "none"

    values = sorted(set(page_numbers))
    ranges: list[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


class PdfInspectionSummary(BaseModel):
    engine: str = "pdf-inspector"
    pdf_type: str
    pdf_type_confidence: float
    page_count: int
    has_encoding_issues: bool
    is_complex_layout: bool
    pages_with_tables: list[int] = Field(default_factory=list)
    pages_with_columns: list[int] = Field(default_factory=list)


class NativePageResult(BaseModel):
    page_idx: int
    markdown: str = ""
    needs_ocr: bool = False
    ocr_reasons: list[str] = Field(default_factory=list)
    extraction_failed: bool = False


class PdfPageRoute(BaseModel):
    page_idx: int
    page_number: int
    parser: Literal["pdf_inspector", "mineru"]
    route_reason: str
    needs_ocr: bool
    ocr_reasons: list[str] = Field(default_factory=list)


class PageFragment(BaseModel):
    page_idx: int
    markdown: str = ""
    blocks: list[NormalizedBlock] = Field(default_factory=list)
    parser: Literal["pdf_inspector", "mineru"]
    route_reason: str
    metadata: dict[str, object] = Field(default_factory=dict)


class PdfInspectorBundle(BaseModel):
    summary: PdfInspectionSummary
    pages: list[NativePageResult] = Field(default_factory=list)
