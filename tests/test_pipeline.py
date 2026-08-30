import json
import unittest.mock
from pathlib import Path

from docchunk.adapters.base import NormalizedDocument
from docchunk.config import AppConfig
from docchunk.errors import ExternalToolError
from docchunk.pipeline import prepare_corpus, split_corpus


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


def test_split_markdown_creates_complete_corpus(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text(
        "# 第一课\n\n" + ("这是一段课程内容。" * 300),
        encoding="utf-8",
    )

    result = split_corpus(source, small_config(tmp_path / "corpora"))

    assert (result / "manifest.json").exists()
    assert (result / "index.jsonl").exists()
    assert (result / "source" / "normalized.md").exists()
    assert (result / "source" / "documents" / "D0001" / "normalized.md").exists()
    assert list((result / "atomic").glob("A*.md"))
    assert list((result / "batches").glob("B*.md"))

    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["documents"] == 1
    assert manifest["counts"]["atomic_chunks"] > 0
    assert manifest["counts"]["reading_batches"] > 0
    assert manifest["documents"][0]["document_id"] == "D0001"


def test_directory_keeps_document_identity(tmp_path: Path) -> None:
    course = tmp_path / "course"
    course.mkdir()
    (course / "1-第一课.md").write_text("# 第一课\n\n" + "甲。" * 200, encoding="utf-8")
    (course / "2-第二课.txt").write_text("第二课。\n\n" + "乙。" * 200, encoding="utf-8")

    result = split_corpus(course, small_config(tmp_path / "corpora"))

    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert [item["document_id"] for item in manifest["documents"]] == ["D0001", "D0002"]
    assert [Path(str(item["source_path"])).name for item in manifest["documents"]] == [
        "1-第一课.md",
        "2-第二课.txt",
    ]

    records = [
        json.loads(line)
        for line in (result / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {"D0001", "D0002"} == {item["document_id"] for item in records}


def test_prepare_only_normalizes_sources(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text("# 标题\n\n正文。", encoding="utf-8")

    corpus = prepare_corpus(source, small_config(tmp_path / "corpora"))

    assert (corpus / "source" / "normalized.md").exists()
    assert not list((corpus / "atomic").glob("A*.md"))
    assert not list((corpus / "batches").glob("B*.md"))


def test_prepare_persists_document_sidecars(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-fake")
    config = small_config(tmp_path / "corpora")
    document = NormalizedDocument(
        source_path=source,
        media_type="text/markdown",
        text="page text",
        sidecars={"page-routing.jsonl": '{"page_idx":0}\n'},
        metadata={"adapter": "smart_pdf", "parser_route": "native_only"},
    )

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter",
        return_value=unittest.mock.Mock(prepare=unittest.mock.Mock(return_value=document)),
    ):
        corpus = prepare_corpus(source, config)

    document_dir = corpus / "source" / "documents" / "D0001"
    assert (document_dir / "page-routing.jsonl").read_text(encoding="utf-8") == '{"page_idx":0}\n'
    source_ref = json.loads((document_dir / "source-ref.json").read_text(encoding="utf-8"))
    assert source_ref["sidecars"]["page-routing.jsonl"].endswith("page-routing.jsonl")


def test_split_writes_structured_processing_log(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text("# 标题\n\n" + "完整内容句子。" * 500, encoding="utf-8")

    corpus = split_corpus(source, small_config(tmp_path / "corpora"))
    log_path = corpus / "logs" / "processing.jsonl"
    assert log_path.exists()

    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {"prepare", "split", "batch"} <= {event["stage"] for event in events}
    assert all(event["status"] != "failed" for event in events)
    # 设计 §23：禁止把全文写进日志
    assert "完整内容句子。" not in log_path.read_text(encoding="utf-8")


def test_prepare_failure_persists_tool_error(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text("# 标题\n\n正文。", encoding="utf-8")
    config = small_config(tmp_path / "corpora")

    with unittest.mock.patch(
        "docchunk.pipeline.choose_adapter",
        side_effect=ExternalToolError("MinerU failed: boom-stderr-12345"),
    ):
        try:
            prepare_corpus(source, config)
        except ExternalToolError:
            pass

    corpus_dirs = list((tmp_path / "corpora").glob("*"))
    assert len(corpus_dirs) == 1
    log_text = (corpus_dirs[0] / "logs" / "processing.jsonl").read_text(encoding="utf-8")
    assert "boom-stderr-12345" in log_text
