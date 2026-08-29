from pathlib import Path

from docchunk.config import AppConfig, resolve_mineru_command
from docchunk.fingerprints import sha256_file, sha256_text, stable_fingerprint
from docchunk.tokenizer import TokenCounter


def test_sha256_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("abc", encoding="utf-8")

    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_text_hashes_utf8_bytes() -> None:
    assert sha256_text("abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_fingerprint_ignores_dict_key_order() -> None:
    assert stable_fingerprint({"a": 1, "b": 2}) == stable_fingerprint({"b": 2, "a": 1})


def test_token_counter_counts_non_empty_text() -> None:
    counter = TokenCounter("o200k_base")
    assert counter.count("这是一个测试。") > 0
    assert counter.count("") == 0


def test_mineru_command_resolution(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "mineru"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    monkeypatch.setattr("docchunk.config.shutil.which", lambda name: str(fake))
    assert resolve_mineru_command() == str(fake)

    monkeypatch.setattr("docchunk.config.shutil.which", lambda name: None)
    monkeypatch.setattr("docchunk.config._MINERU_VENV_FALLBACK", fake)
    assert resolve_mineru_command() == str(fake)

    assert resolve_mineru_command("/custom/mineru") == "/custom/mineru"
    assert AppConfig().mineru_backend == "hybrid-engine"
