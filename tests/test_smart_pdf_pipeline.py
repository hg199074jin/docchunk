"""End-to-end Smart PDF pipeline tests (MinerU/pdf-inspector mocked)."""

import json
import unittest.mock
from pathlib import Path
from unittest.mock import Mock

from docchunk.adapters.base import NormalizedDocument
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorInventoryError
from docchunk.config import AppConfig
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import NativePageResult, PdfInspectionSummary, PdfInspectorBundle
from docchunk.pipeline import split_corpus
from docchunk.verify import verify_corpus


def small_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=100,
        atomic_soft_min_tokens=60,
        atomic_soft_max_tokens=140,
        batch_target_tokens=300,
        batch_soft_min_tokens=200,
        batch_soft_max_tokens=360,
    )


def _summary(page_count: int, **overrides: object) -> PdfInspectionSummary:
    values: dict[str, object] = {
        "pdf_type": "mixed",
        "pdf_type_confidence": 0.8,
        "page_count": page_count,
        "has_encoding_issues": False,
        "is_complex_layout": False,
    }
    values.update(overrides)
    return PdfInspectionSummary(**values)  # type: ignore[arg-type]


def _pdf_pages(count: int, chars_per_page: int = 900) -> list[NativePageResult]:
    return [
        NativePageResult(
            page_idx=idx,
            markdown=f"第{idx + 1}页正文。" + "内" * chars_per_page,
            needs_ocr=False,
        )
        for idx in range(count)
    ]


def _mineru_page_document(path: Path, page_idx: int, text: str) -> NormalizedDocument:
    block = {
        "type": "text",
        "text": text.replace("\n\n", ""),
        "page_idx": 0,
    }
    return NormalizedDocument(
        source_path=path,
        media_type="text/markdown",
        text=text,
        metadata={
            "adapter": "mineru",
            "page_mode": True,
            "source_page_idx": page_idx,
            "_content_list_preview": [block],
        },
    )


def _smart_adapter(
    bundle: PdfInspectorBundle,
    mineru_page_texts: dict[int, str] | None = None,
    mineru_whole_text: str = "整份 OCR 文本。",
) -> SmartPdfAdapter:
    path_holder: dict[str, Path] = {}

    def prepare_page(path: Path, page_idx: int) -> NormalizedDocument:
        path_holder["p"] = path
        text = (mineru_page_texts or {}).get(page_idx, f"第{page_idx + 1}页扫描OCR结果。")
        return _mineru_page_document(path, page_idx, text)

    mineru = Mock()
    mineru.prepare.side_effect = lambda path: _mineru_page_document(
        path, -1, mineru_whole_text
    )
    mineru.prepare_page.side_effect = prepare_page
    inspector = Mock()
    inspector.inspect_and_extract.return_value = bundle
    return SmartPdfAdapter(inspector=inspector, mineru=mineru)


def test_native_only_pdf_pipeline_end_to_end(tmp_path: Path) -> None:
    source = tmp_path / "native.pdf"
    source.write_bytes(b"%PDF-fake")
    bundle = PdfInspectorBundle(
        summary=_summary(3, pdf_type="text_based"),
        pages=_pdf_pages(3),
    )
    adapter = _smart_adapter(bundle)

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter", return_value=adapter
    ):
        corpus = split_corpus(source, small_config(tmp_path / "corpora"))

    doc_dir = corpus / "source" / "documents" / "D0001"
    # A: sidecar 存在且每页一行
    routing = (doc_dir / "page-routing.jsonl").read_text(encoding="utf-8")
    assert len(routing.splitlines()) == 3
    assert all('"parser":"pdf_inspector"' in line for line in routing.splitlines())
    # A: source-ref 摘要正确，manifest 不含逐页正文
    source_ref = json.loads((doc_dir / "source-ref.json").read_text(encoding="utf-8"))
    assert source_ref["adapter"] == "smart_pdf"
    assert source_ref["metadata"]["parser_route"] == "native_only"
    assert source_ref["sidecars"]["page-routing.jsonl"] == (
        "source/documents/D0001/page-routing.jsonl"
    )
    # A: verify 通过
    report = verify_corpus(corpus)
    assert report.ok, report.errors


def test_mixed_pdf_pipeline_keeps_page_provenance(tmp_path: Path) -> None:
    source = tmp_path / "audit.pdf"
    source.write_bytes(b"%PDF-fake")
    pages = _pdf_pages(5, chars_per_page=900)
    pages[0] = NativePageResult(page_idx=0, markdown="", needs_ocr=True, ocr_reasons=["scanned"])
    pages[1] = NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"])
    bundle = PdfInspectorBundle(summary=_summary(5), pages=pages)
    adapter = _smart_adapter(bundle)

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter", return_value=adapter
    ):
        corpus = split_corpus(source, small_config(tmp_path / "corpora"))

    records = [
        json.loads(line)
        for line in (corpus / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records
    # C: 页码 provenance 全部落在 1..5
    for record in records:
        page_start = record["source"]["page_start"]
        page_end = record["source"]["page_end"]
        assert 1 <= page_start <= 5
        assert page_start <= page_end <= 5
    # C: 存在整块落在第 4 页（1-based）的 chunk；最后一块 ending 第 5 页
    assert any(
        r["source"]["page_start"] == 4 and r["source"]["page_end"] == 4 for r in records
    )
    assert records[-1]["source"]["page_end"] == 5

    routing = (
        (corpus / "source" / "documents" / "D0001" / "page-routing.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(routing) == 5
    assert [('"parser":"mineru"' in line) for line in routing] == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert verify_corpus(corpus).ok


def test_blank_page_does_not_shift_page_numbers(tmp_path: Path) -> None:
    source = tmp_path / "with-blank.pdf"
    source.write_bytes(b"%PDF-fake")
    pages = _pdf_pages(3, chars_per_page=900)
    pages[1] = NativePageResult(page_idx=1, markdown="", needs_ocr=False)
    bundle = PdfInspectorBundle(summary=_summary(3), pages=pages)
    adapter = _smart_adapter(bundle)

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter", return_value=adapter
    ):
        corpus = split_corpus(source, small_config(tmp_path / "corpora"))

    records = [
        json.loads(line)
        for line in (corpus / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    # E: 最后一页仍是用户第 3 页，不因空白页左移
    assert records[-1]["source"]["page_end"] == 3
    # 空白页本身没有内容，但页边界分隔符仍保留（页序不变）：
    # 第 1 页结尾 + 两个页边界 = 4 个连续换行
    normalized = (corpus / "source" / "documents" / "D0001" / "normalized.md").read_text(
        encoding="utf-8"
    )
    assert "\n\n\n\n" in normalized


def test_full_fallback_pipeline_when_inventory_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "mismatch.pdf"
    source.write_bytes(b"%PDF-fake")
    mineru = Mock()
    mineru.prepare.return_value = _mineru_page_document(source, -1, "整份OCR。")
    inspector = Mock()
    inspector.inspect_and_extract.side_effect = PdfInspectorInventoryError("mismatch")
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter", return_value=adapter
    ):
        corpus = split_corpus(source, small_config(tmp_path / "corpora"))

    doc_dir = corpus / "source" / "documents" / "D0001"
    mineru.prepare.assert_called_once()  # type: ignore[attr-defined]
    assert not (doc_dir / "page-routing.jsonl").exists()
    source_ref = json.loads((doc_dir / "source-ref.json").read_text(encoding="utf-8"))
    assert source_ref["metadata"]["parser_route"] == "full_mineru_fallback"
    assert (
        source_ref["metadata"]["routing"]["full_fallback_reason"]
        == "page_inventory_mismatch"
    )
    assert verify_corpus(corpus).ok


def test_mineru_page_failure_marks_state_failed(tmp_path: Path) -> None:
    source = tmp_path / "fail.pdf"
    source.write_bytes(b"%PDF-fake")
    pages = [
        NativePageResult(page_idx=0, markdown="第一页。" + "甲" * 300, needs_ocr=False),
        NativePageResult(page_idx=1, markdown="", needs_ocr=True, ocr_reasons=["scanned"]),
    ]
    bundle = PdfInspectorBundle(summary=_summary(2), pages=pages)
    mineru = Mock()
    mineru.prepare_page.side_effect = ExternalToolError("MinerU failed: page boom")
    inspector = Mock()
    inspector.inspect_and_extract.return_value = bundle
    adapter = SmartPdfAdapter(inspector=inspector, mineru=mineru)

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter", return_value=adapter
    ):
        try:
            split_corpus(source, small_config(tmp_path / "corpora"))
        except ExternalToolError:
            pass

    corpus_dirs = list((tmp_path / "corpora").glob("*"))
    assert len(corpus_dirs) == 1
    state = json.loads((corpus_dirs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["stage"] == "failed"
    log_text = (corpus_dirs[0] / "logs" / "processing.jsonl").read_text(encoding="utf-8")
    assert "MinerU failed" in log_text
