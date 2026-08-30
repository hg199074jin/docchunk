from pathlib import Path

from docchunk.adapters.base import DocumentAdapter
from docchunk.adapters.directory import SUPPORTED_SUFFIXES, discover_inputs
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.pandoc import PandocAdapter
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter
from docchunk.adapters.text import TextAdapter
from docchunk.config import AppConfig
from docchunk.errors import UnsupportedInputError
from docchunk.models.pdf import (
    PAGE_SMART_PDF_POLICY_VERSION,
    format_page_ranges,
    page_index_to_number,
)


def choose_adapter(
    path: Path,
    mineru_command: str = "mineru",
    mineru_backend: str = "hybrid-engine",
    mineru_effort: str = "medium",
) -> DocumentAdapter:
    suffix = path.suffix.casefold()

    if suffix in {".md", ".markdown"}:
        return MarkdownAdapter()
    if suffix == ".txt":
        return TextAdapter()
    if suffix == ".docx":
        return PandocAdapter()
    if suffix == ".pdf":
        return SmartPdfAdapter(
            command=mineru_command,
            backend=mineru_backend,
            effort=mineru_effort,
        )

    raise UnsupportedInputError(f"Unsupported input type: {suffix or '<none>'}")


def analyze_input(path: Path, config: AppConfig) -> dict[str, object]:
    """只读分析输入，不生成 Corpus。"""
    path = path.resolve()
    inputs = discover_inputs(path)
    if not inputs:
        raise UnsupportedInputError(f"No supported input files under: {path}")

    total_bytes = sum(item.stat().st_size for item in inputs)

    estimable = [item for item in inputs if item.suffix.casefold() in {".md", ".markdown", ".txt"}]
    needs_conversion = [item.name for item in inputs if item not in estimable]

    estimated_tokens: int | None = None
    if estimable and not needs_conversion:
        from docchunk.tokenizer import TokenCounter

        counter = TokenCounter(config.tokenizer_encoding)
        estimated_tokens = sum(
            counter.count(item.read_text(encoding="utf-8", errors="replace"))
            for item in estimable
        )

    def _adapter_name(item: Path) -> str:
        adapter = choose_adapter(
            item,
            mineru_command=config.mineru_command,
            mineru_backend=config.mineru_backend,
            mineru_effort=config.mineru_effort,
        )
        return type(adapter).__name__

    pdf_inspections: list[dict[str, object]] = []
    for item in inputs:
        if item.suffix.casefold() != ".pdf":
            continue
        try:
            bundle = PdfInspectorAdapter().inspect_and_extract(item)
        except Exception as exc:  # noqa: BLE001 — inspect must report, never call MinerU
            pdf_inspections.append({"file": item.name, "error": str(exc)})
            continue
        summary = bundle.summary
        ocr_pages = [
            page_index_to_number(page.page_idx)
            for page in bundle.pages
            if page.needs_ocr
        ]
        pdf_inspections.append(
            {
                "file": item.name,
                "type": summary.pdf_type,
                "pages": summary.page_count,
                "planned_native": summary.page_count - len(ocr_pages),
                "planned_mineru": len(ocr_pages),
                "ocr_pages": format_page_ranges(ocr_pages),
                "tables": format_page_ranges(summary.pages_with_tables),
                "columns": format_page_ranges(summary.pages_with_columns),
                "encoding_issues": summary.has_encoding_issues,
                "policy": PAGE_SMART_PDF_POLICY_VERSION,
            }
        )

    return {
        "input_type": "directory" if path.is_dir() else "file",
        "file_count": len(inputs),
        "total_bytes": total_bytes,
        "estimated_tokens": estimated_tokens,
        "token_estimate_note": (
            "PDF/DOCX 需要转换后才能获得准确 token"
            if needs_conversion
            else None
        ),
        "files_needing_conversion": needs_conversion,
        "adapters": sorted({_adapter_name(item) for item in inputs}),
        "pdf_inspections": pdf_inspections,
        "atomic_profile": {
            "target_tokens": config.atomic_target_tokens,
            "soft_range": [config.atomic_soft_min_tokens, config.atomic_soft_max_tokens],
        },
        "batch_profile": {
            "target_tokens": config.batch_target_tokens,
            "soft_range": [config.batch_soft_min_tokens, config.batch_soft_max_tokens],
            "overlap_atomic_count": config.overlap_atomic_count,
        },
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
    }
