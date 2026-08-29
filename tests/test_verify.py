from pathlib import Path

from docchunk.config import AppConfig
from docchunk.pipeline import split_corpus
from docchunk.verify import verify_corpus


def verify_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=80,
        atomic_soft_min_tokens=40,
        atomic_soft_max_tokens=100,
        batch_target_tokens=200,
        batch_soft_min_tokens=120,
        batch_soft_max_tokens=240,
    )


def test_verify_passes_for_fresh_corpus(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# 标题\n\n" + ("完整内容。" * 500), encoding="utf-8")

    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))
    report = verify_corpus(corpus)

    assert report.ok is True
    assert report.errors == []


def test_verify_handles_document_relative_offsets(tmp_path: Path) -> None:
    course = tmp_path / "course"
    course.mkdir()
    (course / "1.md").write_text("# 一\n\n" + "甲。" * 300, encoding="utf-8")
    (course / "2.md").write_text("# 二\n\n" + "乙。" * 300, encoding="utf-8")

    corpus = split_corpus(course, verify_config(tmp_path / "corpora"))
    report = verify_corpus(corpus)

    assert report.ok is True


def test_verify_fails_when_atomic_file_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 500, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    first_atomic = min((corpus / "atomic").glob("A*.md"))
    first_atomic.unlink()

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("missing atomic file" in error.lower() for error in report.errors)


def test_verify_fails_when_atomic_body_changes(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 500, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    first_atomic = min((corpus / "atomic").glob("A*.md"))
    original = first_atomic.read_text(encoding="utf-8")
    first_atomic.write_text(original + "被篡改", encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("reconstructed text" in error.lower() for error in report.errors)


def test_verify_fails_when_batch_new_material_is_duplicated(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 800, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    batches = sorted((corpus / "batches").glob("B*.md"))
    assert len(batches) >= 2

    second = batches[1]
    content = second.read_text(encoding="utf-8")
    first_new_line = next(
        line for line in content.splitlines()
        if line.startswith("  - A")
    )
    content = content.replace(
        "new_atomic_ids:\n",
        f"new_atomic_ids:\n{first_new_line}\n",
        1,
    )
    second.write_text(content, encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False


def test_verify_fails_when_source_file_changes(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# 标题\n\n" + "原始内容。" * 200, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    source.write_text("# 标题\n\n" + "被改后的内容。" * 200, encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("source hash changed" in error.lower() for error in report.errors)


def test_verify_fails_when_source_ref_is_tampered(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# 标题\n\n" + "完整内容。" * 200, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    source_ref = corpus / "source" / "documents" / "D0001" / "source-ref.json"
    import json

    data = json.loads(source_ref.read_text(encoding="utf-8"))
    data["adapter"] = "fake-adapter"
    source_ref.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("source-ref.json" in error.lower() for error in report.errors)


def test_verify_warns_when_blocks_jsonl_drift_from_normalized(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# 标题\n\n" + "完整内容。" * 300, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    normalized = corpus / "source" / "documents" / "D0001" / "normalized.md"
    normalized.write_text(normalized.read_text(encoding="utf-8") + "\n追加噪音", encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("normalized source hash mismatch" in error.lower() for error in report.errors)
