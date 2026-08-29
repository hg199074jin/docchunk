import json
from pathlib import Path

from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.storage import (
    append_index_record,
    create_corpus_layout,
    write_atomic_chunk,
)


def test_storage_writes_atomic_and_jsonl(tmp_path: Path) -> None:
    paths = create_corpus_layout(tmp_path, "demo")
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=5,
        char_start=0,
        char_end=4,
        heading_path=["第一章", '带"引号"的小节'],
        source=SourceLocation(file="a.md"),
        flags=AtomicFlags(),
    )

    write_atomic_chunk(paths, record, "正文")
    append_index_record(paths, record)

    atomic = paths.atomic_dir / "A000001.md"
    assert atomic.exists()
    content = atomic.read_text(encoding="utf-8")
    assert content.endswith("\n\n正文")
    assert "A000001" in content

    lines = paths.index_jsonl.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["atomic_id"] == "A000001"


def test_atomic_storage_preserves_body_whitespace(tmp_path: Path) -> None:
    paths = create_corpus_layout(tmp_path, "demo")
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=1,
        char_start=0,
        char_end=8,
        source=SourceLocation(file="a.md"),
    )
    body = "\n正文\n\n"

    write_atomic_chunk(paths, record, body)

    content = (paths.atomic_dir / "A000001.md").read_text(encoding="utf-8")
    assert content.endswith("\n\n" + body)
