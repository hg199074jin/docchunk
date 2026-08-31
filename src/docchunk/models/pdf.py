"""Internal models for page-level smart PDF routing."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from docchunk.adapters.base import NormalizedBlock

PdfTypeName = Literal["text_based", "scanned", "image_based", "mixed"]
PdfParserName = Literal["pdf_inspector", "mineru"]


def page_index_to_number(page_idx: int) -> int:
    """Convert the internal 0-based page index to the user-facing 1-based page number."""
    if page_idx < 0:
        raise ValueError("page_idx must be >= 0")
    return page_idx + 1


def page_number_to_index(page_number: int) -> int:
    """Convert the user-facing 1-based page number to the internal 0-based page index."""
    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    return page_number - 1


class PdfInspectionSummary(BaseModel):
    """Document-level detection summary from pdf-inspector.

    ``pages_with_tables`` / ``pages_with_columns`` keep the library's user-facing
    1-based convention; every other page number in DocChunk is a 0-based page_idx.
    """

    engine: str = "pdf-inspector"
    pdf_type: PdfTypeName
    pdf_type_confidence: float = Field(ge=0.0, le=1.0)
    page_count: int = Field(gt=0)
    has_encoding_issues: bool
    is_complex_layout: bool
    pages_with_tables: list[int] = Field(default_factory=list)
    pages_with_columns: list[int] = Field(default_factory=list)


class NativePageResult(BaseModel):
    """Normalized per-page native extraction result (0-based page_idx)."""

    page_idx: int = Field(ge=0)
    markdown: str
    needs_ocr: bool
    ocr_reasons: list[str] = Field(default_factory=list)
    extraction_failed: bool = False


class PdfPageRoute(BaseModel):
    """Per-page routing decision recorded in page-routing.jsonl."""

    page_idx: int = Field(ge=0)
    page_number: int = Field(ge=1)
    parser: PdfParserName
    route_reason: str
    needs_ocr: bool
    ocr_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_page_number(self) -> "PdfPageRoute":
        if self.page_number != self.page_idx + 1:
            raise ValueError("page_number must equal page_idx + 1")
        return self


class PageFragment(BaseModel):
    """One processed PDF page on its way into the assembler."""

    page_idx: int = Field(ge=0)
    markdown: str
    parser: PdfParserName
    route_reason: str
    needs_ocr: bool
    blocks: list[NormalizedBlock] = Field(default_factory=list)


class PdfInspectorBundle(BaseModel):
    """Detection summary plus normalized per-page native extraction results."""

    summary: PdfInspectionSummary
    pages: list[NativePageResult]
