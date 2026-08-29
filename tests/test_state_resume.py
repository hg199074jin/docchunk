from pathlib import Path
from unittest.mock import patch

import pytest

from docchunk.config import AppConfig
from docchunk.models.state import ProcessingStage
from docchunk.pipeline import load_state, rebuild_batches, split_corpus


def reuse_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=80,
        atomic_soft_min_tokens=40,
        atomic_soft_max_tokens=100,
        batch_target_tokens=200,
        batch_soft_min_tokens=120,
        batch_soft_max_tokens=240,
    )


def test_second_split_reuses_prepared_source(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("内容。" * 500, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")

    first = split_corpus(source, config)

    # pipeline.py 直接 import 了 choose_adapter，所以 patch 必须打在 docchunk.pipeline.choose_adapter。
    with patch("docchunk.pipeline.choose_adapter") as choose:
        second = split_corpus(source, config)

    assert second == first
    choose.assert_not_called()


def test_rebuild_batches_does_not_touch_atomic_files(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("内容。" * 1200, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")
    corpus = split_corpus(source, config)

    before = {
        item.name: item.read_bytes()
        for item in sorted((corpus / "atomic").glob("A*.md"))
    }

    rebuild_batches(
        corpus_path=corpus,
        target_tokens=260,
        soft_min_tokens=160,
        soft_max_tokens=320,
        overlap_atomic_count=1,
    )

    after = {
        item.name: item.read_bytes()
        for item in sorted((corpus / "atomic").glob("A*.md"))
    }

    assert after == before


def test_changed_source_creates_new_corpus_id(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    config = reuse_config(tmp_path / "corpora")

    source.write_text("版本一。" * 300, encoding="utf-8")
    first = split_corpus(source, config)

    source.write_text("版本二。" * 300, encoding="utf-8")
    second = split_corpus(source, config)

    assert first != second
    assert first.exists()
    assert second.exists()


def test_failed_pipeline_records_failed_state(tmp_path: Path) -> None:
    source = tmp_path / "bad.docx"
    source.write_bytes(b"not-a-real-docx")
    config = reuse_config(tmp_path / "corpora")

    with patch(
        "docchunk.pipeline._prepare_one_document",
        side_effect=RuntimeError("boom"),
    ):
        try:
            split_corpus(source, config)
        except RuntimeError:
            pass

    corpus_dirs = list((tmp_path / "corpora").glob("*"))
    assert len(corpus_dirs) == 1
    state = load_state(corpus_dirs[0])
    assert state.stage is ProcessingStage.FAILED
    assert "boom" in (state.error or "")


def test_split_failure_does_not_destroy_existing_atomic(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 400, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")

    first_corpus = split_corpus(source, config)
    original_hash = (first_corpus / "atomic" / "A000001.md").read_bytes()

    # 用 staging 重写路径时（force=True），split_atomic 抛错；
    # C2 要求旧 atomic 与 manifest 都不能被破坏。
    with patch(
        "docchunk.pipeline.split_atomic",
        side_effect=RuntimeError("corrupt splitter"),
    ):
        from docchunk.pipeline import split_prepared_corpus

        try:
            split_prepared_corpus(first_corpus, config, force=True)
        except RuntimeError:
            pass

    assert (first_corpus / "atomic" / "A000001.md").read_bytes() == original_hash
    # staging 残留必须清理
    staging = first_corpus.parent / f".{first_corpus.name}.staging"
    assert not staging.exists()


def test_rebuild_batches_raises_rebuild_error_on_verify_fail(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("内容。" * 800, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")
    corpus = split_corpus(source, config)

    from docchunk.errors import RebuildError

    with patch("docchunk.verify.verify_corpus") as fake_verify:
        from docchunk.verify import VerificationReport

        fake_verify.return_value = VerificationReport(
            ok=False,
            errors=["forced mismatch"],
        )

        with pytest.raises(RebuildError, match="Rebuilt batches failed verification"):
            rebuild_batches(
                corpus_path=corpus,
                target_tokens=200,
                soft_min_tokens=120,
                soft_max_tokens=240,
                overlap_atomic_count=1,
            )
