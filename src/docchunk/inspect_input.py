from pathlib import Path

from docchunk.adapters.base import DocumentAdapter
from docchunk.adapters.directory import SUPPORTED_SUFFIXES, discover_inputs
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.pandoc import PandocAdapter
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter, PdfInspectorInventoryError
from docchunk.adapters.text import TextAdapter
from docchunk.config import PAGE_SMART_PDF_POLICY_VERSION, AppConfig
from docchunk.errors import UnsupportedInputError
from docchunk.models.pdf import page_index_to_number


def compact_page_ranges(page_numbers: list[int]) -> str:
    """Render 1-based page numbers compactly, e.g. ``1-3, 21, 84-85``."""
    if not page_numbers:
        return ""

    ordered = sorted(page_numbers)
    runs: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        runs.append((start, previous))
        start = previous = number
    runs.append((start, previous))

    return ", ".join(
        f"{lo}-{hi}" if hi > lo else f"{lo}" for lo, hi in runs
    )


def _planned_total(entries: list[dict[str, object]], key: str) -> int:
    total = 0
    for entry in entries:
        value = entry.get(key, 0)
        if isinstance(value, int):
            total += value
    return total


def _pdf_preflight_entry(item: Path) -> dict[str, object]:
    """Run the full pdf-inspector preflight for one PDF; MinerU is never called."""
    entry: dict[str, object] = {
        "file": item.name,
        "route_policy": PAGE_SMART_PDF_POLICY_VERSION,
    }
    try:
        bundle = PdfInspectorAdapter().inspect_and_extract(item)
    except PdfInspectorInventoryError as exc:
        entry["full_fallback_reason"] = "page_inventory_mismatch"
        entry["full_fallback_detail"] = f"{type(exc).__name__}: {exc}"
        entry["mineru_invocation"] = "whole_document"
        return entry
    except Exception as exc:  # noqa: BLE001 — 外部库边界，preflight 失败也要给出计划
        entry["full_fallback_reason"] = "pdf_inspector_failed"
        entry["full_fallback_detail"] = f"{type(exc).__name__}: {exc}"
        entry["mineru_invocation"] = "whole_document"
        return entry

    summary = bundle.summary
    ocr_pages = [
        page_index_to_number(page.page_idx)
        for page in bundle.pages
        if page.needs_ocr
    ]
    unlocalized = summary.has_encoding_issues and not ocr_pages

    entry.update(
        {
            "pdf_type": summary.pdf_type,
            "pdf_type_confidence": summary.pdf_type_confidence,
            "page_count": summary.page_count,
            "planned_native_pages": summary.page_count - len(ocr_pages),
            "planned_mineru_pages": summary.page_count if unlocalized else len(ocr_pages),
            "ocr_pages": [] if unlocalized else ocr_pages,
            "has_encoding_issues": summary.has_encoding_issues,
            "pages_with_tables": summary.pages_with_tables,
            "pages_with_columns": summary.pages_with_columns,
            "mineru_invocation": (
                "whole_document"
                if unlocalized or len(ocr_pages) == summary.page_count
                else "per_page"
            ),
        }
    )
    if unlocalized:
        entry["full_fallback_reason"] = "unlocalized_encoding_issue"
    return entry


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
        # v1.1：PDF 唯一入口是 SmartPdfAdapter，逐页路由 native/OCR（设计 §5）
        return SmartPdfAdapter(
            mineru_command=mineru_command,
            mineru_backend=mineru_backend,
            mineru_effort=mineru_effort,
        )

    raise UnsupportedInputError(f"Unsupported input type: {suffix or '<none>'}")


def analyze_input(path: Path, config: AppConfig) -> dict[str, object]:
    """只读分析输入，不生成 Corpus。"""
    path = path.resolve()
    inputs = discover_inputs(path)
    if not inputs:
        raise UnsupportedInputError(f"No supported input files under: {path}")

    total_bytes = sum(item.stat().st_size for item in inputs)

    pdf_items = [item for item in inputs if item.suffix.casefold() == ".pdf"]
    pdf_entries = [_pdf_preflight_entry(item) for item in pdf_items]
    planned_native_total = _planned_total(pdf_entries, "planned_native_pages")
    planned_mineru_total = _planned_total(pdf_entries, "planned_mineru_pages")

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
        "pdf_files": pdf_entries,
        "planned_native_pages_total": planned_native_total,
        "planned_mineru_pages_total": planned_mineru_total,
        "adapters": sorted({_adapter_name(item) for item in inputs}),
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
