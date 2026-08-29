import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from docchunk.models.index import AtomicIndexRecord
from docchunk.models.manifest import Manifest, utc_now_iso


@dataclass(frozen=True)
class CorpusPaths:
    root: Path
    source_dir: Path
    atomic_dir: Path
    batches_dir: Path
    logs_dir: Path
    manifest_json: Path
    index_jsonl: Path
    combined_md: Path
    state_json: Path


def create_corpus_layout(root: Path, corpus_id: str) -> CorpusPaths:
    corpus_root = root / corpus_id
    paths = CorpusPaths(
        root=corpus_root,
        source_dir=corpus_root / "source",
        atomic_dir=corpus_root / "atomic",
        batches_dir=corpus_root / "batches",
        logs_dir=corpus_root / "logs",
        manifest_json=corpus_root / "manifest.json",
        index_jsonl=corpus_root / "index.jsonl",
        combined_md=corpus_root / "combined.md",
        state_json=corpus_root / "state.json",
    )

    for directory in (
        paths.root,
        paths.source_dir,
        paths.atomic_dir,
        paths.batches_dir,
        paths.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return paths


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_atomic_chunk(
    paths: CorpusPaths,
    record: AtomicIndexRecord,
    text: str,
) -> None:
    target = paths.root / record.path
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f"atomic_id: {_yaml_string(record.atomic_id)}",
        f"document_id: {_yaml_string(record.document_id)}",
        f"sequence: {record.sequence}",
        f"tokens: {record.token_count}",
        f"source_file: {_yaml_string(record.source.file)}",
        (
            "page_start: null"
            if record.source.page_start is None
            else f"page_start: {record.source.page_start}"
        ),
        (
            "page_end: null"
            if record.source.page_end is None
            else f"page_end: {record.source.page_end}"
        ),
    ]

    if record.heading_path:
        lines.append("heading_path:")
        lines.extend(f"  - {_yaml_string(item)}" for item in record.heading_path)
    else:
        lines.append("heading_path: []")

    lines.extend(["---", "", text])
    target.write_text("\n".join(lines), encoding="utf-8")


def append_index_record(paths: CorpusPaths, record: AtomicIndexRecord) -> None:
    with paths.index_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def write_manifest(paths: CorpusPaths, manifest: Manifest) -> None:
    manifest.updated_at = utc_now_iso()
    paths.manifest_json.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )


def read_atomic_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Atomic file has no frontmatter: {path}")

    closing = content.find("\n---\n", 4)
    if closing < 0:
        raise ValueError(f"Atomic frontmatter is not closed: {path}")

    body_start = closing + len("\n---\n")
    if content[body_start:body_start + 1] == "\n":
        body_start += 1
    return content[body_start:]


def write_combined_view(
    paths: CorpusPaths,
    records: list[AtomicIndexRecord],
) -> None:
    lines = [
        "# docchunk Combined Atomic View",
        "",
        (
            "> 这是派生阅读视图。权威原文是 source/documents/*/normalized.md；"
            "权威切片索引是 index.jsonl。"
        ),
        "",
    ]

    for record in records:
        atomic_path = paths.root / record.path
        body = read_atomic_body(atomic_path)
        lines.extend(
            [
                f"## {record.atomic_id}",
                "",
                f"- document_id: `{record.document_id}`",
                f"- source: `{record.source.file}`",
                f"- char_range: `{record.char_start}:{record.char_end}`",
                (
                    f"- pages: `{record.source.page_start}-{record.source.page_end}`"
                    if record.source.page_start is not None
                    else "- pages: `n/a`"
                ),
                "",
                body,
                "",
            ]
        )

    paths.combined_md.write_text("\n".join(lines), encoding="utf-8")


def clear_generated_files(directory: Path, pattern: str) -> None:
    for target in directory.glob(pattern):
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
