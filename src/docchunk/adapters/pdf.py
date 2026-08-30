from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedBlock, NormalizedDocument
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import (
    PAGE_SMART_PDF_POLICY_VERSION,
    PageFragment,
    PdfInspectorBundle,
    PdfPageRoute,
    page_index_to_number,
)


def _page_block(fragment: PageFragment) -> list[NormalizedBlock]:
    if not fragment.markdown:
        return []
    if fragment.blocks:
        return fragment.blocks
    return [
        NormalizedBlock(
            block_index=0,
            char_start=0,
            char_end=len(fragment.markdown),
            text=fragment.markdown,
            page_idx=fragment.page_idx,
        )
    ]


def assemble_page_fragments(
    path: Path,
    fragments: list[PageFragment],
    *,
    metadata: dict[str, object],
    routes: list[PdfPageRoute],
) -> NormalizedDocument:
    """Assemble page-local Markdown and offsets into one normalized document."""
    ordered = sorted(fragments, key=lambda item: item.page_idx)
    if [item.page_idx for item in ordered] != list(range(len(ordered))):
        raise ValueError("Page fragments must cover each page exactly once from page 0")

    text_parts: list[str] = []
    blocks: list[NormalizedBlock] = []
    document_offset = 0
    block_index = 0
    for fragment_index, fragment in enumerate(ordered):
        if fragment_index:
            text_parts.append("\n\n")
            document_offset += 2

        markdown = fragment.markdown
        text_parts.append(markdown)
        for block in _page_block(fragment):
            blocks.append(
                block.model_copy(
                    update={
                        "block_index": block_index,
                        "char_start": document_offset + block.char_start,
                        "char_end": document_offset + block.char_end,
                        "page_idx": fragment.page_idx,
                    }
                )
            )
            block_index += 1
        document_offset += len(markdown)

    routing_lines = "".join(route.model_dump_json() + "\n" for route in routes)
    final_metadata = dict(metadata)
    final_metadata.update(
        {
            "adapter": "smart_pdf",
            "parser_route": _parser_route(routes),
            "routing_policy": PAGE_SMART_PDF_POLICY_VERSION,
            "native_pages": sum(route.parser == "pdf_inspector" for route in routes),
            "mineru_pages": sum(route.parser == "mineru" for route in routes),
            "routing": {
                "policy": PAGE_SMART_PDF_POLICY_VERSION,
                "native_pages": sum(route.parser == "pdf_inspector" for route in routes),
                "mineru_pages": sum(route.parser == "mineru" for route in routes),
                "page_routing_sidecar": "page-routing.jsonl",
            },
        }
    )
    return NormalizedDocument(
        source_path=path,
        media_type="text/markdown",
        text="".join(text_parts),
        blocks=blocks,
        metadata=final_metadata,
        sidecars={"page-routing.jsonl": routing_lines},
    )


def _parser_route(routes: list[PdfPageRoute]) -> str:
    parsers = {route.parser for route in routes}
    if parsers == {"pdf_inspector"}:
        return "native_only"
    if parsers == {"mineru"}:
        return "mineru_only"
    return "mixed"


class SmartPdfAdapter(DocumentAdapter):
    def __init__(
        self,
        command: str = "mineru",
        backend: str = "hybrid-engine",
        effort: str = "medium",
    ) -> None:
        self.inspector = PdfInspectorAdapter()
        self.mineru = MinerUAdapter(command=command, backend=backend, effort=effort)

    def prepare(self, path: Path) -> NormalizedDocument:
        try:
            bundle = self.inspector.inspect_and_extract(path)
        except Exception:  # noqa: BLE001 — inspector failure uses safe whole-PDF fallback
            return self._whole_pdf_fallback(path, reason="pdf_inspector_failed")

        expected_indexes = list(range(bundle.summary.page_count))
        actual_indexes = sorted(page.page_idx for page in bundle.pages)
        if actual_indexes != expected_indexes:
            return self._whole_pdf_fallback(path, reason="page_inventory_mismatch", bundle=bundle)

        if bundle.summary.has_encoding_issues and not any(
            page.needs_ocr or page.ocr_reasons for page in bundle.pages
        ):
            return self._whole_pdf_fallback(
                path,
                reason="unlocalized_encoding_issue",
                bundle=bundle,
            )

        fragments: list[PageFragment] = []
        routes: list[PdfPageRoute] = []
        for page in sorted(bundle.pages, key=lambda item: item.page_idx):
            if page.needs_ocr:
                route_reason = page.ocr_reasons[0] if page.ocr_reasons else "needs_ocr"
                try:
                    fragment = self.mineru.prepare_page(path, page.page_idx)
                except ExternalToolError as exc:
                    page_number = page_index_to_number(page.page_idx)
                    raise ExternalToolError(
                        f"MinerU failed for {path} page {page_number} "
                        f"(route_reason={route_reason}): {exc}"
                    ) from exc
                fragments.append(fragment.model_copy(update={"route_reason": route_reason}))
                routes.append(
                    PdfPageRoute(
                        page_idx=page.page_idx,
                        page_number=page_index_to_number(page.page_idx),
                        parser="mineru",
                        route_reason=route_reason,
                        needs_ocr=True,
                        ocr_reasons=page.ocr_reasons,
                    )
                )
                continue

            fragments.append(
                PageFragment(
                    page_idx=page.page_idx,
                    markdown=page.markdown,
                    parser="pdf_inspector",
                    route_reason="native_text_safe",
                )
            )
            routes.append(
                PdfPageRoute(
                    page_idx=page.page_idx,
                    page_number=page_index_to_number(page.page_idx),
                    parser="pdf_inspector",
                    route_reason="native_text_safe",
                    needs_ocr=False,
                    ocr_reasons=[],
                )
            )

        return assemble_page_fragments(
            path,
            fragments,
            metadata={"pdf_inspection": bundle.summary.model_dump()},
            routes=routes,
        )

    def _whole_pdf_fallback(
        self,
        path: Path,
        *,
        reason: str,
        bundle: PdfInspectorBundle | None = None,
    ) -> NormalizedDocument:
        document = self.mineru.prepare(path)
        metadata = dict(document.metadata)
        metadata.update(
            {
                "adapter": "smart_pdf",
                "parser_route": "full_mineru_fallback",
                "fallback_reason": reason,
                "routing_policy": PAGE_SMART_PDF_POLICY_VERSION,
                "routing": {
                    "policy": PAGE_SMART_PDF_POLICY_VERSION,
                    "native_pages": 0,
                    "mineru_pages": (
                        bundle.summary.page_count if bundle is not None else None
                    ),
                    "page_routing_sidecar": "page-routing.jsonl",
                },
            }
        )
        if bundle is not None:
            metadata["pdf_inspection"] = bundle.summary.model_dump()

        sidecars: dict[str, str] = {}
        if bundle is not None:
            routes = [
                PdfPageRoute(
                    page_idx=page_idx,
                    page_number=page_index_to_number(page_idx),
                    parser="mineru",
                    route_reason=reason,
                    needs_ocr=True,
                    ocr_reasons=[reason],
                )
                for page_idx in range(bundle.summary.page_count)
            ]
            sidecars["page-routing.jsonl"] = "".join(
                route.model_dump_json() + "\n" for route in routes
            )
            metadata["native_pages"] = 0
            metadata["mineru_pages"] = bundle.summary.page_count
        return document.model_copy(update={"metadata": metadata, "sidecars": sidecars})
