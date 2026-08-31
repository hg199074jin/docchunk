import json
from pathlib import Path

import pytest

from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.storage import (
    append_index_record,
    create_corpus_layout,
    write_atomic_chunk,
    write_document_sidecars,
)


def test_write_document_sidecars_writes_only_basename_files(tmp_path: Path) -> None:
    written = write_document_sidecars(
        tmp_path,
        {"page-routing.jsonl": '{"page_idx":0}\n'},
    )

    assert written == {"page-routing.jsonl": "page-routing.jsonl"}
    assert (tmp_path / "page-routing.jsonl").read_text(encoding="utf-8") == '{"page_idx":0}\n'


def test_write_document_sidecars_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_document_sidecars(tmp_path, {"../escape.txt": "bad"})


def test_write_document_sidecars_rejects_nested_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_document_sidecars(tmp_path, {"sub/dir.jsonl": "bad"})


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
