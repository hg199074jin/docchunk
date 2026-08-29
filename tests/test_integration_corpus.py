import json
import shutil
import subprocess
from pathlib import Path

import pytest

from docchunk.config import AppConfig
from docchunk.pipeline import split_corpus
from docchunk.verify import verify_corpus

GOLDEN_DOC = Path("tests/fixtures/golden-doc.md")


def golden_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=120,
        atomic_soft_min_tokens=60,
        atomic_soft_max_tokens=180,
        batch_target_tokens=300,
        batch_soft_min_tokens=180,
        batch_soft_max_tokens=360,
    )


def _batch_id_lists(path: Path) -> tuple[list[str], list[str]]:
    overlap: list[str] = []
    new: list[str] = []
    section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "overlap_atomic_ids:":
            section = "overlap"
        elif line == "new_atomic_ids:":
            section = "new"
        elif line.startswith("  - A") and section == "overlap":
            overlap.append(line[4:].strip())
        elif line.startswith("  - A") and section == "new":
            new.append(line[4:].strip())
        elif line == "---" and section is not None:
            break
    return overlap, new


def test_markdown_golden_is_stable(tmp_path: Path) -> None:
    corpus = split_corpus(GOLDEN_DOC, golden_config(tmp_path / "corpora"))

    records = [
        json.loads(line)
        for line in (corpus / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) == 3
    assert [(r["char_start"], r["char_end"]) for r in records] == [
        (0, 149),
        (149, 365),
        (365, 629),
    ]
    assert records[0]["heading_path"] == ["第一章 总论"]
    assert records[1]["heading_path"] == ["第一章 总论", "1.2 方法概述"]
    assert records[2]["heading_path"] == ["第二章 流程"]

    batch_files = sorted((corpus / "batches").glob("B*.md"))
    assert [path.name for path in batch_files] == ["B0001.md", "B0002.md"]
    assert _batch_id_lists(batch_files[0]) == ([], ["A000001", "A000002"])
    assert _batch_id_lists(batch_files[1]) == (["A000002"], ["A000003"])

    report = verify_corpus(corpus)
    assert report.ok is True


def test_directory_set_orders_naturally(tmp_path: Path) -> None:
    course = tmp_path / "course"
    course.mkdir()
    (course / "1-第一课.md").write_text("# 第一课\n\n" + "甲。" * 400, encoding="utf-8")
    (course / "2-第二课.txt").write_text("第二课。\n\n" + "乙。" * 400, encoding="utf-8")
    (course / "10-第十课.md").write_text("# 第十课\n\n" + "丙。" * 400, encoding="utf-8")

    corpus = split_corpus(course, golden_config(tmp_path / "corpora"))

    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    assert [item["document_id"] for item in manifest["documents"]] == [
        "D0001",
        "D0002",
        "D0003",
    ]
    assert [Path(str(item["source_path"])).name for item in manifest["documents"]] == [
        "1-第一课.md",
        "2-第二课.txt",
        "10-第十课.md",
    ]

    records = [
        json.loads(line)
        for line in (corpus / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["document_id"] for record in records] == sorted(
        (record["document_id"] for record in records),
        key=lambda d: d,
    )
    assert {record["document_id"] for record in records} == {"D0001", "D0002", "D0003"}
    sequences = [record["sequence"] for record in records]
    assert sequences == list(range(1, len(records) + 1))

    report = verify_corpus(corpus)
    assert report.ok is True


def _build_simple_pdf(path: Path, pages: list[list[str]]) -> None:
    """生成一个两页文本 PDF（Helvetica，ASCII），供 MinerU 冒烟测试使用。"""

    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    objects: list[bytes] = []
    page_count = len(pages)
    content_start = 4
    font_id = content_start + page_count * 2

    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    for index, lines in enumerate(pages):
        page_id = 3 + index * 2
        content_id = page_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        stream_lines = ["BT /F1 12 Tf 72 720 Td 18 TL"]
        for line in lines:
            stream_lines.append(f"({escape(line)}) Tj T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")

    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


@pytest.mark.external
def test_pandoc_docx_roundtrip(tmp_path: Path) -> None:
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")

    source_md = tmp_path / "book.md"
    source_md.write_text(
        "# 标题\n\n" + "这是正文段落。" * 500 + "\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    docx = tmp_path / "book.docx"
    subprocess.run(
        ["pandoc", str(source_md), "-f", "markdown", "-t", "docx", "-o", str(docx)],
        check=True,
    )

    config = golden_config(tmp_path / "corpora")
    corpus = split_corpus(docx, config)

    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["documents"][0]["adapter"] == "pandoc"
    assert verify_corpus(corpus).ok is True


@pytest.mark.external
def test_mineru_pdf_produces_page_provenance(tmp_path: Path) -> None:
    pdf = tmp_path / "sample-book.pdf"
    _build_simple_pdf(
        pdf,
        [
            [
                "Sample Book Chapter One",
                "This page exists to validate MinerU page provenance.",
                "The pipeline must map atomic chunks back to page numbers.",
            ],
            [
                "Sample Book Chapter Two",
                "The second page continues the corpus with more prose.",
                "Verification reconstructs the normalized source exactly.",
            ],
        ],
    )

    config = golden_config(tmp_path / "corpora")
    corpus = split_corpus(pdf, config)

    records = [
        json.loads(line)
        for line in (corpus / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records, "PDF corpus must produce atomic chunks"
    assert any(record["source"]["page_start"] is not None for record in records)
    assert verify_corpus(corpus).ok is True
