"""Page assembler for page-level smart PDF routing.

Turns per-page :class:`PageFragment` results (from pdf-inspector native
extraction, per-page MinerU OCR, or whole-document MinerU fallback) into a
single :class:`NormalizedDocument` with original page order preserved and
document-global character offsets.

Markdown merging rules (design §22): pages are joined with ``\n\n``; no
``--- Page N ---`` style markers are ever injected — page numbers live in
provenance, not in the text.
"""

from pathlib import Path

from docchunk.adapters.base import (
    NormalizedBlock,
    NormalizedDocument,
    normalize_line_endings,
)
from docchunk.config import PAGE_SMART_PDF_POLICY_VERSION
from docchunk.models.pdf import PageFragment, PdfInspectionSummary, PdfPageRoute

PAGE_ROUTING_SIDECAR = "page-routing.jsonl"


def render_page_routing_jsonl(routes: list[PdfPageRoute]) -> str:
    """Render the per-page audit sidecar: one line per original PDF page."""
    return "".join(route.model_dump_json() + "\n" for route in routes)


def _parser_route(routes: list[PdfPageRoute], page_count: int) -> str:
    mineru_pages = sum(route.parser == "mineru" for route in routes)
    if mineru_pages == 0:
        return "native_only"
    if mineru_pages == page_count:
        return "mineru_only"
    return "mixed"


def assemble_page_fragments(
    path: Path,
    summary: PdfInspectionSummary,
    fragments: list[PageFragment],
    routes: list[PdfPageRoute],
) -> NormalizedDocument:
    """Assemble page fragments into one NormalizedDocument.

    Requires exactly one fragment per original page (0..page_count-1). Blank
    pages keep their route record but produce no body block, so page numbers
    never drift.
    """
    ordered = sorted(fragments, key=lambda item: item.page_idx)
    actual = [item.page_idx for item in ordered]
    expected = list(range(summary.page_count))
    if actual != expected:
        raise ValueError(
            "PDF page fragments do not cover the full document "
            f"(expected pages {expected}, got {actual})"
        )

    parts: list[str] = []
    blocks: list[NormalizedBlock] = []
    cursor = 0
    block_index = 0

    for position, fragment in enumerate(ordered):
        if position > 0:
            parts.append("\n\n")
            cursor += 2

        text = normalize_line_endings(fragment.markdown)
        parts.append(text)

        if text:
            blocks.append(
                NormalizedBlock(
                    block_index=block_index,
                    char_start=cursor,
                    char_end=cursor + len(text),
                    text=text,
                    page_idx=fragment.page_idx,
                )
            )
            block_index += 1
        cursor += len(text)

    native_pages = sum(route.parser == "pdf_inspector" for route in routes)

    return NormalizedDocument(
        source_path=path,
        media_type="application/pdf",
        text="".join(parts),
        blocks=blocks,
        metadata={
            "adapter": "smart_pdf",
            "parser_route": _parser_route(routes, summary.page_count),
            "pdf_inspection": summary.model_dump(),
            "routing": {
                "policy": PAGE_SMART_PDF_POLICY_VERSION,
                "native_pages": native_pages,
                "mineru_pages": summary.page_count - native_pages,
                "page_routing_sidecar": PAGE_ROUTING_SIDECAR,
            },
        },
        sidecars={PAGE_ROUTING_SIDECAR: render_page_routing_jsonl(routes)},
    )
