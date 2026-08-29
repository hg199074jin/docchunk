from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from docchunk.fingerprints import sha256_file, sha256_text
from docchunk.models.index import AtomicIndexRecord
from docchunk.models.manifest import Manifest, utc_now_iso
from docchunk.storage import read_atomic_body
from docchunk.tokenizer import TokenCounter


class VerificationReport(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _load_records(corpus_path: Path) -> list[AtomicIndexRecord]:
    index_path = corpus_path / "index.jsonl"
    records: list[AtomicIndexRecord] = []

    for line_number, line in enumerate(
        index_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            records.append(AtomicIndexRecord.model_validate_json(line))
        except Exception as exc:  # 单行损坏必须带行号报告
            raise ValueError(f"Invalid index.jsonl line {line_number}: {exc}") from exc

    return records


def _batch_id_lists(path: Path) -> tuple[list[str], list[str]]:
    overlap: list[str] = []
    new: list[str] = []
    section: str | None = None
    fence_count = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "---":
            fence_count += 1
            if fence_count >= 2:
                break
            continue

        if line == "overlap_atomic_ids:":
            section = "overlap"
            continue
        if line == "new_atomic_ids:":
            section = "new"
            continue

        if line.startswith("  - A"):
            atomic_id = line[4:].strip()
            if section == "overlap":
                overlap.append(atomic_id)
            elif section == "new":
                new.append(atomic_id)

    return overlap, new


def verify_corpus(
    corpus_path: Path,
    persist: bool = True,
) -> VerificationReport:
    corpus_path = corpus_path.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = corpus_path / "manifest.json"
    index_path = corpus_path / "index.jsonl"

    if not manifest_path.exists():
        return VerificationReport(
            ok=False,
            errors=["Missing manifest.json"],
        )
    if not index_path.exists():
        return VerificationReport(
            ok=False,
            errors=["Missing index.jsonl"],
        )

    try:
        manifest = Manifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001 — 损坏的 manifest 必须转化为报告而不是崩溃
        return VerificationReport(
            ok=False,
            errors=[f"Invalid manifest.json: {exc}"],
        )

    try:
        records = _load_records(corpus_path)
    except ValueError as exc:
        return VerificationReport(ok=False, errors=[str(exc)])

    expected_sequences = list(range(1, len(records) + 1))
    actual_sequences = [record.sequence for record in records]
    if actual_sequences != expected_sequences:
        errors.append(
            "Atomic sequence is not contiguous from 1 to N"
        )

    expected_ids = [f"A{number:06d}" for number in expected_sequences]
    actual_ids = [record.atomic_id for record in records]
    if actual_ids != expected_ids:
        errors.append("Atomic IDs do not match sequence order")

    counter = TokenCounter(manifest.tokenizer.encoding)
    by_document: dict[str, list[AtomicIndexRecord]] = defaultdict(list)

    for record in records:
        by_document[record.document_id].append(record)

        atomic_path = corpus_path / record.path
        if not atomic_path.exists():
            errors.append(f"Missing atomic file: {record.path}")
            continue

        body = read_atomic_body(atomic_path)
        actual_tokens = counter.count(body)
        if actual_tokens != record.token_count:
            errors.append(
                f"Token count mismatch for {record.atomic_id}: "
                f"index={record.token_count}, actual={actual_tokens}"
            )

        if record.char_end < record.char_start:
            errors.append(
                f"Invalid char range for {record.atomic_id}: "
                f"{record.char_start}>{record.char_end}"
            )

        if len(body) != record.char_end - record.char_start:
            errors.append(
                f"Character length mismatch for {record.atomic_id}"
            )

    document_entries = {
        str(item["document_id"]): dict(item)
        for item in manifest.documents
    }

    for document_id, document_records in by_document.items():
        entry = document_entries.get(document_id)
        if entry is None:
            errors.append(f"Index references unknown document: {document_id}")
            continue

        normalized_path = corpus_path / str(entry["normalized_path"])
        if not normalized_path.exists():
            errors.append(
                f"Missing normalized document for {document_id}: "
                f"{entry['normalized_path']}"
            )
            continue

        normalized = normalized_path.read_text(encoding="utf-8")
        reconstructed_parts: list[str] = []
        expected_start = 0

        for record in document_records:
            if record.char_start != expected_start:
                errors.append(
                    f"Non-contiguous char offsets in {document_id}: "
                    f"expected {expected_start}, got {record.char_start} "
                    f"at {record.atomic_id}"
                )

            atomic_path = corpus_path / record.path
            if atomic_path.exists():
                reconstructed_parts.append(read_atomic_body(atomic_path))

            expected_start = record.char_end

        reconstructed = "".join(reconstructed_parts)
        if reconstructed != normalized:
            errors.append(
                f"Reconstructed text does not match normalized source for {document_id}"
            )

        if document_records and document_records[-1].char_end != len(normalized):
            errors.append(
                f"Final char_end does not reach normalized source end for {document_id}"
            )

        expected_normalized_hash = entry.get("normalized_sha256")
        if isinstance(expected_normalized_hash, str):
            actual_hash = sha256_text(normalized)
            if actual_hash != expected_normalized_hash:
                errors.append(
                    f"Normalized source hash mismatch for {document_id}"
                )

        expected_source_sha = entry.get("source_sha256")
        source_path_str = entry.get("source_path")
        if isinstance(expected_source_sha, str) and isinstance(source_path_str, str):
            original_path = Path(source_path_str)
            if original_path.exists():
                actual_source_sha = sha256_file(original_path)
                if actual_source_sha != expected_source_sha:
                    errors.append(
                        f"Source hash changed for {document_id}: "
                        f"recorded {expected_source_sha[:12]}... but current "
                        f"file is {actual_source_sha[:12]}..."
                    )
            else:
                errors.append(
                    f"Original source file is missing for {document_id}: "
                    f"{original_path}"
                )

        source_ref_path = corpus_path / "source" / "documents" / document_id / "source-ref.json"
        if source_ref_path.exists():
            try:
                import json

                ref_data = json.loads(source_ref_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"Invalid source-ref.json for {document_id}: {exc}")
            else:
                for field in (
                    "source_sha256",
                    "normalized_sha256",
                    "adapter",
                    "normalized_path",
                ):
                    recorded = ref_data.get(field)
                    if recorded is None:
                        errors.append(
                            f"source-ref.json for {document_id} is missing field: {field}"
                        )
                        continue
                    expected = entry.get(field)
                    if expected is not None and recorded != expected:
                        errors.append(
                            f"source-ref.json for {document_id} mismatch on "
                            f"{field}: recorded={recorded!r} expected={expected!r}"
                        )
        else:
            errors.append(f"Missing source-ref.json for {document_id}")

    batch_files = sorted((corpus_path / "batches").glob("B*.md"))
    all_new_ids: list[str] = []
    previous_new_ids: list[str] = []

    for batch_index, batch_path in enumerate(batch_files):
        overlap_ids, new_ids = _batch_id_lists(batch_path)

        for atomic_id in overlap_ids + new_ids:
            if atomic_id not in actual_ids:
                errors.append(
                    f"{batch_path.name} references unknown Atomic {atomic_id}"
                )

        if set(overlap_ids) & set(new_ids):
            errors.append(
                f"{batch_path.name} contains the same Atomic as overlap and new material"
            )

        if len(new_ids) != len(set(new_ids)):
            errors.append(
                f"{batch_path.name} contains duplicate new_atomic_ids"
            )

        expected_overlap = (
            previous_new_ids[-manifest.batch_policy.overlap_atomic_count :]
            if batch_index > 0 and manifest.batch_policy.overlap_atomic_count > 0
            else []
        )
        if overlap_ids != expected_overlap:
            errors.append(
                f"{batch_path.name} overlap does not match previous Batch tail"
            )

        all_new_ids.extend(new_ids)
        previous_new_ids = new_ids

        batch_tokens = counter.count(batch_path.read_text(encoding="utf-8"))
        if batch_tokens > manifest.batch_policy.soft_max_tokens:
            warnings.append(
                f"{batch_path.name} has {batch_tokens} tokens, above "
                f"batch soft max {manifest.batch_policy.soft_max_tokens}"
            )

    if all_new_ids != actual_ids:
        errors.append(
            "Batch new_atomic_ids do not cover all Atomic IDs exactly once and in order"
        )

    if records:
        forced_count = sum(record.flags.forced_split for record in records)
        forced_ratio = forced_count / len(records)
        if forced_ratio > 0.05:
            warnings.append(
                f"Forced split ratio is {forced_ratio:.1%}; inspect OCR/text quality"
            )

    for entry in manifest.documents:
        entry_dict = dict(entry)
        source_path = str(entry_dict.get("source_path", ""))
        if not source_path.lower().endswith(".pdf"):
            continue

        document_id = str(entry_dict["document_id"])
        pdf_records = by_document.get(document_id, [])
        if pdf_records and not any(
            record.source.page_start is not None
            for record in pdf_records
        ):
            warnings.append(
                f"PDF document {document_id} has no page provenance"
            )

        metadata = entry_dict.get("metadata")
        if isinstance(metadata, dict):
            unaligned = metadata.get("unaligned_blocks")
            if isinstance(unaligned, int) and unaligned > 0:
                warnings.append(
                    f"{document_id} has {unaligned} MinerU blocks that "
                    "could not be aligned to normalized Markdown"
                )

    ok = not errors

    if persist:
        manifest.verification.status = "passed" if ok else "failed"
        manifest.verification.checked_at = utc_now_iso()
        manifest.verification.errors = errors
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

        from docchunk.models.state import CorpusState, ProcessingStage

        state = (
            CorpusState.model_validate_json(
                (corpus_path / "state.json").read_text(encoding="utf-8")
            )
            if (corpus_path / "state.json").exists()
            else CorpusState()
        )
        state.stage = ProcessingStage.READY if ok else ProcessingStage.FAILED
        state.error = None if ok else "Corpus verification failed"
        (corpus_path / "state.json").write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return VerificationReport(
        ok=ok,
        errors=errors,
        warnings=warnings,
    )
