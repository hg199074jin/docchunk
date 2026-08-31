import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from docchunk.adapters.base import NormalizedBlock, NormalizedDocument
from docchunk.adapters.directory import discover_inputs
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.batching.builder import build_batches
from docchunk.config import AppConfig
from docchunk.errors import ExternalToolError
from docchunk.fingerprints import sha256_file, sha256_text, stable_fingerprint
from docchunk.inspect_input import choose_adapter
from docchunk.logging_utils import EventLogger
from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.models.manifest import (
    AtomicPolicy,
    BatchPolicy,
    CorpusCounts,
    CorpusFingerprints,
    Manifest,
    TokenizerConfig,
)
from docchunk.models.state import CorpusState, ProcessingStage
from docchunk.provenance.pages import source_pages_for_span
from docchunk.splitting.atomic import split_atomic
from docchunk.storage import (
    CorpusPaths,
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


def load_state(corpus_path: Path) -> CorpusState:
    state_path = corpus_path / "state.json"
    if not state_path.exists():
        return CorpusState()
    return CorpusState.model_validate_json(
        state_path.read_text(encoding="utf-8")
    )


def write_state(corpus_path: Path, state: CorpusState) -> None:
    (corpus_path / "state.json").write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _set_stage(
    corpus_path: Path,
    stage: ProcessingStage,
    *,
    error: str | None = None,
) -> None:
    state = load_state(corpus_path)
    state.stage = stage
    state.error = error
    write_state(corpus_path, state)


def _installed_version(package: str) -> str:
    try:
        return package_version(package)
    except PackageNotFoundError:
        return "not-installed"


def _normalization_fingerprint(config: AppConfig) -> str:
    return stable_fingerprint(
        {
            "docx_adapter": "pandoc",
            "pdf_adapter": "mineru",
            "docx_fallback_to_mineru": config.docx_fallback_to_mineru,
        }
    )


def _atomic_policy_fingerprint(
    manifest: Manifest,
) -> str:
    return stable_fingerprint(
        {
            "tokenizer": manifest.tokenizer.model_dump(),
            "atomic_policy": manifest.atomic_policy.model_dump(),
            "splitter_backend": "semantic-text-splitter",
            "splitter_version": _installed_version("semantic-text-splitter"),
            "schema_version": manifest.schema_version,
        }
    )


def _batch_policy_fingerprint(
    manifest: Manifest,
) -> str:
    return stable_fingerprint(
        {
            "batch_policy": manifest.batch_policy.model_dump(),
            "batch_renderer": "v1",
            "schema_version": manifest.schema_version,
        }
    )


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


def _prepare_documents(
    paths: CorpusPaths,
    inputs: list[Path],
    config: AppConfig,
    counter: TokenCounter,
    logger: EventLogger,
) -> tuple[list[dict[str, object]], int]:
    documents: list[dict[str, object]] = []
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
        logger.log(
            "prepare",
            "completed",
            f"normalized {source.name}",
            document_id=document_id,
            extra={
                "adapter": document.metadata.get("adapter", "direct"),
                "source_sha256": source_hash,
            },
        )

    return documents, normalized_tokens


def prepare_corpus(
    input_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
    input_path = input_path.resolve()
    inputs = discover_inputs(input_path)
    if not inputs:
        raise ValueError("No supported input files found")

    inventory = _source_inventory(input_path, inputs)
    source_fingerprint = stable_fingerprint(inventory)
    title = input_path.stem if input_path.is_file() else input_path.name
    corpus_id = make_corpus_id(title, source_fingerprint)
    paths = create_corpus_layout(config.corpus_root, corpus_id)
    logger = EventLogger(paths.logs_dir / "processing.jsonl", echo=config.verbose)

    atomic_policy, batch_policy = _policies_from_config(config)
    normalization_fp = _normalization_fingerprint(config)
    counter = TokenCounter(config.tokenizer_encoding)

    if paths.manifest_json.exists() and not force:
        existing = Manifest.model_validate_json(
            paths.manifest_json.read_text(encoding="utf-8")
        )
        if (
            existing.fingerprints.source == source_fingerprint
            and existing.fingerprints.normalization == normalization_fp
        ):
            # prepare 阶段可以复用 normalized source，但要把“本次请求的”
            # Atomic/Batch policy 写回 Manifest。后续阶段通过 fingerprint
            # 判断是否只重切 Atomic 或只重建 Batch。
            existing.atomic_policy = atomic_policy
            existing.batch_policy = batch_policy
            write_manifest(paths, existing)
            logger.log(
                "prepare",
                "reused",
                "source fingerprint matched; normalized documents reused",
            )
            return paths.root

    _set_stage(paths.root, ProcessingStage.PREPARING)
    logger.log("prepare", "started", f"preparing {len(inputs)} input file(s)")

    try:
        documents, normalized_tokens = _prepare_documents(
            paths=paths,
            inputs=inputs,
            config=config,
            counter=counter,
            logger=logger,
        )
    except Exception as exc:
        logger.tool_error("prepare", exc)
        _set_stage(
            paths.root,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

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
        fingerprints=CorpusFingerprints(
            source=source_fingerprint,
            normalization=normalization_fp,
        ),
    )
    write_manifest(paths, manifest)
    _set_stage(paths.root, ProcessingStage.PREPARED)
    logger.log(
        "prepare",
        "completed",
        f"corpus {corpus_id} prepared",
        extra={"documents": len(documents)},
    )
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


def split_prepared_corpus(
    corpus_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )

    expected_atomic_fp = _atomic_policy_fingerprint(manifest)
    atomic_files = list((corpus_path / "atomic").glob("A*.md"))
    logger = EventLogger(corpus_path / "logs" / "processing.jsonl", echo=config.verbose)
    if (
        not force
        and manifest.fingerprints.atomic_policy == expected_atomic_fp
        and (corpus_path / "index.jsonl").exists()
        and atomic_files
    ):
        logger.log(
            "split",
            "reused",
            "atomic policy fingerprint matched; keeping existing Atomic chunks",
        )
        return corpus_path

    manifest.verification.status = "pending"
    manifest.verification.checked_at = None
    manifest.verification.errors = []
    write_manifest(
        create_corpus_layout(corpus_path.parent, corpus_path.name),
        manifest,
    )
    _set_stage(corpus_path, ProcessingStage.SPLITTING)
    logger.log("split", "started", "splitting prepared documents into Atomic chunks")

    try:
        counter = TokenCounter(manifest.tokenizer.encoding)

        # 先在临时目录写入新 Atomic 集合；成功后再原子替换旧目录，
        # 避免失败时 atomic 与 manifest 出现不可解释的部分状态。
        staging_root = corpus_path.parent / f".{corpus_path.name}.staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_paths = create_corpus_layout(staging_root.parent, staging_root.name)
        staging_atomic_dir = staging_paths.root / "atomic"
        staging_cleaned = False

        atomic_dir = corpus_path / "atomic"
        index_path = corpus_path / "index.jsonl"
        index_path.write_text("", encoding="utf-8")

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
                write_atomic_chunk(staging_paths, record, chunk.text)
                append_index_record(staging_paths, record)
                records_for_combined.append(record)

        write_combined_view(staging_paths, records_for_combined)
        manifest.counts.atomic_chunks = global_sequence
        manifest.fingerprints.atomic_policy = expected_atomic_fp

        # 成功后原子地替换 atomic/ 与 index.jsonl（保留旧 atomic 至 rename 完成）
        if atomic_dir.exists():
            for old in atomic_dir.glob("A*.md"):
                old.unlink()
        else:
            atomic_dir.mkdir(parents=True, exist_ok=True)
        for record in records_for_combined:
            src = staging_atomic_dir / f"{record.atomic_id}.md"
            dst = atomic_dir / f"{record.atomic_id}.md"
            src.replace(dst)
        staging_index = staging_paths.index_jsonl
        index_path.write_text(
            staging_index.read_text(encoding="utf-8"), encoding="utf-8"
        )

        # 重写 combined.md 到正式 corpus 根
        write_combined_view(
            create_corpus_layout(corpus_path.parent, corpus_path.name),
            records_for_combined,
        )

        manifest_path = corpus_path / "manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        # 清理 staging
        staging_cleaned = True
    except Exception as exc:
        logger.tool_error("split", exc)
        _set_stage(
            corpus_path,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        import shutil as _shutil_final

        if not staging_cleaned and staging_root.exists():
            _shutil_final.rmtree(staging_root, ignore_errors=True)

    _set_stage(corpus_path, ProcessingStage.SPLIT)
    logger.log(
        "split",
        "completed",
        f"{global_sequence} atomic chunks written",
        extra={"atomic_chunks": global_sequence},
    )
    return corpus_path


def _load_atomic_records(corpus_path: Path) -> list[AtomicIndexRecord]:
    records: list[AtomicIndexRecord] = []
    for line in (corpus_path / "index.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(AtomicIndexRecord.model_validate_json(line))
    return records


def batch_corpus(
    corpus_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )

    expected_batch_fp = _batch_policy_fingerprint(manifest)
    batch_files = list((corpus_path / "batches").glob("B*.md"))
    logger = EventLogger(corpus_path / "logs" / "processing.jsonl", echo=config.verbose)
    if (
        not force
        and manifest.fingerprints.batch_policy == expected_batch_fp
        and batch_files
    ):
        logger.log(
            "batch",
            "reused",
            "batch policy fingerprint matched; keeping existing Batches",
        )
        return corpus_path

    manifest.verification.status = "pending"
    manifest.verification.checked_at = None
    manifest.verification.errors = []
    write_manifest(
        create_corpus_layout(corpus_path.parent, corpus_path.name),
        manifest,
    )
    _set_stage(corpus_path, ProcessingStage.BATCHING)
    logger.log("batch", "started", "building reading batches")

    try:
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
        manifest.fingerprints.batch_policy = expected_batch_fp
        write_manifest(
            create_corpus_layout(corpus_path.parent, corpus_path.name),
            manifest,
        )
    except Exception as exc:
        logger.tool_error("batch", exc)
        _set_stage(
            corpus_path,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    _set_stage(corpus_path, ProcessingStage.BATCHED)
    logger.log(
        "batch",
        "completed",
        f"{len(batches)} reading batches written",
        extra={"reading_batches": len(batches)},
    )
    return corpus_path


def split_corpus(
    input_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
    corpus = prepare_corpus(input_path, config, force=force)

    try:
        split_prepared_corpus(corpus, config, force=force)
        batch_corpus(corpus, config, force=force)
        return corpus
    except Exception as exc:
        _set_stage(
            corpus,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise


def rebuild_batches(
    corpus_path: Path,
    target_tokens: int,
    soft_min_tokens: int,
    soft_max_tokens: int,
    overlap_atomic_count: int,
) -> Path:
    corpus_path = corpus_path.resolve()
    manifest_path = corpus_path / "manifest.json"
    manifest = Manifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    if not (0 < soft_min_tokens <= target_tokens <= soft_max_tokens):
        raise ValueError(
            "Batch token values must satisfy: "
            "0 < soft_min <= target <= soft_max"
        )

    manifest.batch_policy = BatchPolicy(
        target_tokens=target_tokens,
        soft_min_tokens=soft_min_tokens,
        soft_max_tokens=soft_max_tokens,
        overlap_atomic_count=overlap_atomic_count,
    )
    manifest.fingerprints.batch_policy = ""
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )

    result = batch_corpus(
        corpus_path,
        AppConfig(),
        force=True,
    )

    from docchunk.verify import verify_corpus

    report = verify_corpus(result)
    if not report.ok:
        from docchunk.errors import RebuildError

        raise RebuildError(
            "Rebuilt batches failed verification: " + "; ".join(report.errors)
        )
    return result


def corpus_status(corpus_path: Path) -> dict[str, object]:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    state = load_state(corpus_path)

    return {
        "corpus_id": manifest.corpus_id,
        "stage": state.stage.value,
        "documents": manifest.counts.documents,
        "atomic_chunks": manifest.counts.atomic_chunks,
        "reading_batches": manifest.counts.reading_batches,
        "verification": manifest.verification.status,
        "source_fingerprint": manifest.fingerprints.source,
        "tokenizer": manifest.tokenizer.encoding,
        "atomic_policy": manifest.atomic_policy.model_dump(),
        "batch_policy": manifest.batch_policy.model_dump(),
        "last_error": state.error,
    }
