import json
from pathlib import Path

from docchunk.adapters.base import NormalizedBlock, NormalizedDocument
from docchunk.adapters.directory import discover_inputs
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.batching.builder import build_batches
from docchunk.config import AppConfig
from docchunk.errors import ExternalToolError
from docchunk.fingerprints import sha256_file, sha256_text, stable_fingerprint
from docchunk.inspect_input import choose_adapter
from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.models.manifest import (
    AtomicPolicy,
    BatchPolicy,
    CorpusCounts,
    Manifest,
    TokenizerConfig,
)
from docchunk.provenance.mineru import source_pages_for_span
from docchunk.splitting.atomic import split_atomic
from docchunk.storage import (
    append_index_record,
    create_corpus_layout,
    read_atomic_body,
    write_atomic_chunk,
    write_combined_view,
    write_manifest,
)
from docchunk.tokenizer import TokenCounter


def make_corpus_id(title: str, source_fingerprint: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in title).strip("-").lower()
    safe = "-".join(part for part in safe.split("-") if part)
    return f"{safe[:48] or 'corpus'}-{source_fingerprint[:12]}"


def _source_inventory(input_path: Path, inputs: list[Path]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    for source in inputs:
        if input_path.is_dir():
            display_path = str(source.relative_to(input_path))
        else:
            display_path = source.name

        items.append(
            {
                "relative_path": display_path,
                "sha256": sha256_file(source),
            }
        )

    return items


def _prepare_one_document(
    source: Path,
    config: AppConfig,
) -> NormalizedDocument:
    adapter = choose_adapter(
        source,
        mineru_command=config.mineru_command,
        mineru_backend=config.mineru_backend,
        mineru_effort=config.mineru_effort,
    )

    try:
        return adapter.prepare(source)
    except ExternalToolError:
        if source.suffix.casefold() != ".docx" or not config.docx_fallback_to_mineru:
            raise

        fallback = MinerUAdapter(
            command=config.mineru_command,
            backend=config.mineru_backend,
            effort=config.mineru_effort,
        )
        document = fallback.prepare(source)
        metadata = dict(document.metadata)
        metadata["adapter_fallback"] = True
        metadata["fallback_from"] = "pandoc"
        return document.model_copy(update={"metadata": metadata})


def _write_normalized_document(
    corpus_root: Path,
    document_id: str,
    document: NormalizedDocument,
    source_sha256: str,
) -> dict[str, object]:
    document_dir = corpus_root / "source" / "documents" / document_id
    document_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = document_dir / "normalized.md"
    normalized_path.write_text(document.text, encoding="utf-8")

    blocks_path = document_dir / "blocks.jsonl"
    with blocks_path.open("w", encoding="utf-8") as handle:
        for block in document.blocks:
            handle.write(block.model_dump_json())
            handle.write("\n")

    source_ref = {
        "source_path": str(document.source_path.resolve()),
        "source_sha256": source_sha256,
        "media_type": document.media_type,
        "adapter": document.metadata.get("adapter", "direct"),
        "adapter_fallback": bool(document.metadata.get("adapter_fallback", False)),
        "normalized_path": str(normalized_path.relative_to(corpus_root)),
        "blocks_path": str(blocks_path.relative_to(corpus_root)),
        "normalized_sha256": sha256_text(document.text),
        "metadata": document.metadata,
    }

    (document_dir / "source-ref.json").write_text(
        json.dumps(source_ref, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return source_ref


def _policies_from_config(
    config: AppConfig,
) -> tuple[AtomicPolicy, BatchPolicy]:
    atomic = AtomicPolicy(
        target_tokens=config.atomic_target_tokens,
        soft_min_tokens=config.atomic_soft_min_tokens,
        soft_max_tokens=config.atomic_soft_max_tokens,
    )
    batch = BatchPolicy(
        target_tokens=config.batch_target_tokens,
        soft_min_tokens=config.batch_soft_min_tokens,
        soft_max_tokens=config.batch_soft_max_tokens,
        overlap_atomic_count=config.overlap_atomic_count,
    )
    return atomic, batch


def prepare_corpus(input_path: Path, config: AppConfig) -> Path:
    input_path = input_path.resolve()
    inputs = discover_inputs(input_path)
    if not inputs:
        raise ValueError("No supported input files found")

    inventory = _source_inventory(input_path, inputs)
    source_fingerprint = stable_fingerprint(inventory)
    title = input_path.stem if input_path.is_file() else input_path.name
    corpus_id = make_corpus_id(title, source_fingerprint)
    paths = create_corpus_layout(config.corpus_root, corpus_id)

    atomic_policy, batch_policy = _policies_from_config(config)
    documents: list[dict[str, object]] = []
    counter = TokenCounter(config.tokenizer_encoding)
    normalized_tokens = 0

    for number, source in enumerate(inputs, start=1):
        document_id = f"D{number:04d}"
        document = _prepare_one_document(source, config)
        source_hash = sha256_file(source)

        source_ref = _write_normalized_document(
            corpus_root=paths.root,
            document_id=document_id,
            document=document,
            source_sha256=source_hash,
        )
        source_ref["document_id"] = document_id
        documents.append(source_ref)
        normalized_tokens += counter.count(document.text)

    # 单文件提供一个便利入口，目录仍以 documents/Dxxxx 为权威。
    if len(documents) == 1:
        normalized_rel = str(documents[0]["normalized_path"])
        normalized_text = (paths.root / normalized_rel).read_text(encoding="utf-8")
        (paths.source_dir / "normalized.md").write_text(normalized_text, encoding="utf-8")

    manifest = Manifest(
        corpus_id=corpus_id,
        title=title,
        source_type="directory" if input_path.is_dir() else "file",
        tokenizer=TokenizerConfig(
            provider="tiktoken",
            encoding=config.tokenizer_encoding,
        ),
        atomic_policy=atomic_policy,
        batch_policy=batch_policy,
        documents=documents,
        normalization={
            "source_fingerprint": source_fingerprint,
            "input_path": str(input_path),
            "docx_fallback_to_mineru": config.docx_fallback_to_mineru,
        },
        counts=CorpusCounts(
            documents=len(documents),
            normalized_tokens=normalized_tokens,
        ),
    )
    write_manifest(paths, manifest)
    return paths.root


def _load_prepared_document(
    corpus_root: Path,
    document_entry: dict[str, object],
) -> NormalizedDocument:
    normalized_rel = str(document_entry["normalized_path"])
    blocks_rel = str(document_entry["blocks_path"])
    text = (corpus_root / normalized_rel).read_text(encoding="utf-8")

    blocks: list[NormalizedBlock] = []
    blocks_file = corpus_root / blocks_rel
    if blocks_file.exists():
        for line in blocks_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                blocks.append(NormalizedBlock.model_validate_json(line))

    return NormalizedDocument(
        source_path=Path(str(document_entry["source_path"])),
        media_type=str(document_entry["media_type"]),
        text=text,
        blocks=blocks,
        metadata={
            "adapter": document_entry.get("adapter", "direct"),
            "adapter_fallback": document_entry.get("adapter_fallback", False),
        },
    )


def _source_location_for_chunk(
    document: NormalizedDocument,
    char_start: int,
    char_end: int,
) -> SourceLocation:
    page_start, page_end = source_pages_for_span(
        document.blocks,
        char_start=char_start,
        char_end=char_end,
    )

    overlapping_blocks = [
        block.block_index
        for block in document.blocks
        if block.char_start < char_end and block.char_end > char_start
    ]

    return SourceLocation(
        file=document.source_path.name,
        page_start=page_start,
        page_end=page_end,
        block_start=min(overlapping_blocks) if overlapping_blocks else None,
        block_end=max(overlapping_blocks) if overlapping_blocks else None,
    )


def split_prepared_corpus(corpus_path: Path, config: AppConfig) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    counter = TokenCounter(manifest.tokenizer.encoding)

    atomic_dir = corpus_path / "atomic"
    atomic_dir.mkdir(exist_ok=True)
    for old in atomic_dir.glob("A*.md"):
        old.unlink()

    index_path = corpus_path / "index.jsonl"
    index_path.write_text("", encoding="utf-8")

    paths = create_corpus_layout(corpus_path.parent, corpus_path.name)
    global_sequence = 0
    records_for_combined: list[AtomicIndexRecord] = []

    for raw_entry in manifest.documents:
        entry = dict(raw_entry)
        document_id = str(entry["document_id"])
        document = _load_prepared_document(corpus_path, entry)

        chunks = split_atomic(
            text=document.text,
            counter=counter,
            policy=manifest.atomic_policy,
            markdown=document.media_type == "text/markdown",
        )

        for chunk in chunks:
            global_sequence += 1
            atomic_id = f"A{global_sequence:06d}"
            source_location = _source_location_for_chunk(
                document,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )

            context: dict[str, str] = {}
            if chunk.table_header_context is not None:
                context["table_header"] = chunk.table_header_context

            record = AtomicIndexRecord(
                atomic_id=atomic_id,
                document_id=document_id,
                sequence=global_sequence,
                path=f"atomic/{atomic_id}.md",
                token_count=chunk.token_count,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                heading_path=chunk.heading_path,
                source=source_location,
                flags=AtomicFlags(
                    forced_split=chunk.forced_split,
                    split_table=chunk.split_table,
                    adapter_fallback=bool(entry.get("adapter_fallback", False)),
                ),
                context=context,
            )
            write_atomic_chunk(paths, record, chunk.text)
            append_index_record(paths, record)
            records_for_combined.append(record)

    write_combined_view(paths, records_for_combined)
    manifest.counts.atomic_chunks = global_sequence
    write_manifest(paths, manifest)
    return corpus_path


def _load_atomic_records(corpus_path: Path) -> list[AtomicIndexRecord]:
    records: list[AtomicIndexRecord] = []
    for line in (corpus_path / "index.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(AtomicIndexRecord.model_validate_json(line))
    return records


def batch_corpus(corpus_path: Path, config: AppConfig) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    records = _load_atomic_records(corpus_path)
    if not records:
        raise ValueError("Corpus has no Atomic chunks; run split first")

    atomic_texts = {
        record.atomic_id: read_atomic_body(corpus_path / record.path)
        for record in records
    }
    atomic_contexts = {
        record.atomic_id: record.context
        for record in records
        if record.context
    }

    counter = TokenCounter(manifest.tokenizer.encoding)
    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=counter,
        policy=manifest.batch_policy,
        atomic_contexts=atomic_contexts,
    )

    batches_dir = corpus_path / "batches"
    batches_dir.mkdir(exist_ok=True)
    for old in batches_dir.glob("B*.md"):
        old.unlink()

    for batch in batches:
        (batches_dir / f"{batch.batch_id}.md").write_text(
            batch.text,
            encoding="utf-8",
        )

    manifest.counts.reading_batches = len(batches)
    paths = create_corpus_layout(corpus_path.parent, corpus_path.name)
    write_manifest(paths, manifest)
    return corpus_path


def split_corpus(input_path: Path, config: AppConfig) -> Path:
    corpus = prepare_corpus(input_path, config)
    split_prepared_corpus(corpus, config)
    batch_corpus(corpus, config)
    return corpus
