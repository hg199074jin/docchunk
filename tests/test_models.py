from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.models.manifest import AtomicPolicy, BatchPolicy, Manifest, TokenizerConfig
from docchunk.models.state import CorpusState, ProcessingStage


def test_manifest_round_trip() -> None:
    manifest = Manifest(
        corpus_id="demo-abc123",
        title="Demo",
        source_type="file",
        tokenizer=TokenizerConfig(provider="tiktoken", encoding="o200k_base"),
        atomic_policy=AtomicPolicy(
            target_tokens=6000,
            soft_min_tokens=4000,
            soft_max_tokens=8000,
        ),
        batch_policy=BatchPolicy(
            target_tokens=24000,
            soft_min_tokens=16000,
            soft_max_tokens=32000,
            overlap_atomic_count=1,
        ),
    )

    restored = Manifest.model_validate_json(manifest.model_dump_json())
    assert restored.corpus_id == "demo-abc123"
    assert restored.atomic_policy.target_tokens == 6000


def test_atomic_record_keeps_provenance() -> None:
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=1234,
        char_start=0,
        char_end=100,
        heading_path=["第一章"],
        source=SourceLocation(
            file="book.pdf",
            page_start=1,
            page_end=2,
        ),
        flags=AtomicFlags(),
    )

    assert record.source.page_start == 1
    assert record.flags.forced_split is False


def test_state_defaults_to_new() -> None:
    state = CorpusState()
    assert state.stage is ProcessingStage.NEW
