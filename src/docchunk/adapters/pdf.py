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
    DocumentAdapter,
    NormalizedBlock,
    NormalizedDocument,
    normalize_line_endings,
)
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter, PdfInspectorInventoryError
from docchunk.config import PAGE_SMART_PDF_POLICY_VERSION
from docchunk.models.pdf import (
    NativePageResult,
    PageFragment,
    PdfInspectionSummary,
    PdfInspectorBundle,
    PdfPageRoute,
    page_index_to_number,
)

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
    # 页边界 "\n\n" 不属于任何一页原文；吸收进下一个非空页 block 的前缀，
    # 避免分隔符落进任何 page block 之外、被切出无页码 provenance 的碎 chunk。
    pending_boundaries = 0

    for position, fragment in enumerate(ordered):
        if position > 0:
            parts.append("\n\n")
            cursor += 2
            pending_boundaries += 1

        text = normalize_line_endings(fragment.markdown)
        parts.append(text)
        cursor += len(text)

        if not text:
            continue

        prefix = "\n\n" * pending_boundaries
        pending_boundaries = 0
        block_text = prefix + text
        blocks.append(
            NormalizedBlock(
                block_index=block_index,
                char_start=cursor - len(block_text),
                char_end=cursor,
                text=block_text,
                page_idx=fragment.page_idx,
            )
        )
        block_index += 1

    if blocks and pending_boundaries:
        # 尾部空白页留下的分隔符归最后一个 block，保证全文被 block 覆盖
        last = blocks[-1]
        blocks[-1] = last.model_copy(
            update={
                "char_end": cursor,
                "text": last.text + "\n\n" * pending_boundaries,
            }
        )

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


def _route_for(page: NativePageResult, parser: str, reason: str) -> PdfPageRoute:
    return PdfPageRoute(
        page_idx=page.page_idx,
        page_number=page_index_to_number(page.page_idx),
        parser=parser,  # type: ignore[arg-type]
        route_reason=reason,
        needs_ocr=page.needs_ocr,
        ocr_reasons=list(page.ocr_reasons),
    )


class SmartPdfAdapter(DocumentAdapter):
    """Route each PDF page to the most reliable parser (design §2/§10).

    Mixed PDFs keep native-safe pages on pdf-inspector and send only
    ``needs_ocr`` pages to MinerU one page at a time. Pure scanned PDFs (all
    pages need OCR) take the whole-document MinerU shortcut in a single call
    (方案 A, design §16.1). Detection failures fall back to whole-document
    MinerU rather than guessing.
    """

    def __init__(
        self,
        inspector: PdfInspectorAdapter | None = None,
        mineru: MinerUAdapter | None = None,
        *,
        mineru_command: str = "mineru",
        mineru_backend: str = "hybrid-engine",
        mineru_effort: str = "medium",
    ) -> None:
        self.inspector = inspector or PdfInspectorAdapter()
        self.mineru = mineru or MinerUAdapter(
            command=mineru_command,
            backend=mineru_backend,
            effort=mineru_effort,
        )

    def prepare(self, path: Path) -> NormalizedDocument:
        try:
            bundle = self.inspector.inspect_and_extract(path)
        except PdfInspectorInventoryError as exc:
            return self._prepare_full_mineru_fallback(
                path,
                reason="page_inventory_mismatch",
                detail=f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 — 外部库边界，任何失败都整份兜底
            return self._prepare_full_mineru_fallback(
                path,
                reason="pdf_inspector_failed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        if self._has_unlocalized_encoding_issue(bundle):
            document = self._prepare_whole_mineru(
                path,
                bundle,
                parser_route="full_mineru_fallback",
                extra_routing={"full_fallback_reason": "unlocalized_encoding_issue"},
                route_reason="unlocalized_encoding_issue",
            )
            return document

        if all(page.needs_ocr for page in bundle.pages):
            # 方案 A（设计 §16.1）：纯扫描 PDF，整份一次调用而非 N 次模型加载
            return self._prepare_whole_mineru(
                path,
                bundle,
                parser_route="mineru_only",
                route_reason="needs_ocr",
            )

        return self._prepare_per_page(path, bundle)

    @staticmethod
    def _has_unlocalized_encoding_issue(bundle: PdfInspectorBundle) -> bool:
        if not bundle.summary.has_encoding_issues:
            return False
        return not any(
            page.needs_ocr or page.ocr_reasons or page.extraction_failed
            for page in bundle.pages
        )

    def _prepare_per_page(
        self,
        path: Path,
        bundle: PdfInspectorBundle,
    ) -> NormalizedDocument:
        fragments: list[PageFragment] = []
        routes: list[PdfPageRoute] = []

        for page in bundle.pages:
            if page.needs_ocr or page.extraction_failed:
                mineru_doc = self.mineru.prepare_page(path, page.page_idx)
                markdown = mineru_doc.text
                parser = "mineru"
                reason = "native_extraction_failed" if page.extraction_failed else "needs_ocr"
            else:
                markdown = page.markdown
                parser = "pdf_inspector"
                reason = "native_text_safe"

            fragments.append(
                PageFragment(
                    page_idx=page.page_idx,
                    markdown=markdown,
                    parser=parser,  # type: ignore[arg-type]
                    route_reason=reason,
                    needs_ocr=page.needs_ocr,
                )
            )
            routes.append(_route_for(page, parser, reason))

        document = assemble_page_fragments(path, bundle.summary, fragments, routes)
        metadata = dict(document.metadata)
        raw_routing = metadata["routing"]
        assert isinstance(raw_routing, dict)  # assembler 固定写入 dict
        routing = dict(raw_routing)
        routing["mineru_invocation"] = "per_page"
        metadata["routing"] = routing
        return document.model_copy(update={"metadata": metadata})

    def _prepare_whole_mineru(
        self,
        path: Path,
        bundle: PdfInspectorBundle,
        *,
        parser_route: str,
        route_reason: str,
        extra_routing: dict[str, str] | None = None,
    ) -> NormalizedDocument:
        document = self.mineru.prepare(path)
        routes = [
            PdfPageRoute(
                page_idx=page.page_idx,
                page_number=page_index_to_number(page.page_idx),
                parser="mineru",
                route_reason=route_reason,
                needs_ocr=page.needs_ocr,
                ocr_reasons=list(page.ocr_reasons),
            )
            for page in bundle.pages
        ]

        metadata = dict(document.metadata)
        metadata["adapter"] = "smart_pdf"
        metadata["parser_route"] = parser_route
        metadata["pdf_inspection"] = bundle.summary.model_dump()
        routing: dict[str, object] = {
            "policy": PAGE_SMART_PDF_POLICY_VERSION,
            "native_pages": 0,
            "mineru_pages": bundle.summary.page_count,
            "page_routing_sidecar": PAGE_ROUTING_SIDECAR,
            "mineru_invocation": "whole_document",
        }
        if extra_routing:
            routing.update(extra_routing)
        metadata["routing"] = routing

        return document.model_copy(
            update={
                "media_type": "application/pdf",
                "metadata": metadata,
                "sidecars": {PAGE_ROUTING_SIDECAR: render_page_routing_jsonl(routes)},
            }
        )

    def _prepare_full_mineru_fallback(
        self,
        path: Path,
        *,
        reason: str,
        detail: str | None = None,
    ) -> NormalizedDocument:
        document = self.mineru.prepare(path)

        metadata = dict(document.metadata)
        metadata["adapter"] = "smart_pdf"
        metadata["parser_route"] = "full_mineru_fallback"
        routing: dict[str, object] = {
            "policy": PAGE_SMART_PDF_POLICY_VERSION,
            "full_fallback_reason": reason,
            "mineru_invocation": "whole_document",
        }
        # detail 只含异常类型与消息，禁止携带 PDF 全文（Logging Contract）
        if detail:
            routing["full_fallback_detail"] = detail
        metadata["routing"] = routing

        # page inventory 不可信：不允许伪造逐页 route 行（设计 §27/§44 Case 10）
        return document.model_copy(
            update={"media_type": "application/pdf", "metadata": metadata}
        )
