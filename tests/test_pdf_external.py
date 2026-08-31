"""Real external-tool tests for Smart PDF Routing (MinerU + pdf-inspector).

These tests exercise the actual local tools: the real pdf-inspector native
extraction, real ``sips``/``cupsfilter`` scan rasterization, and real
MinerU page parsing. They are marked ``external`` and skipped from fast CI.
"""

import shutil
import subprocess
import zlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_integration_corpus import _build_simple_pdf

from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter
from docchunk.config import resolve_mineru_command

pytestmark = pytest.mark.external


def _mineru_or_skip() -> MinerUAdapter:
    if resolve_mineru_command("mineru") == "mineru":
        pytest.skip("mineru not installed")
    return MinerUAdapter()


def _rasterize_to_scan_pdf(source_pdf: Path, workdir: Path) -> Path:
    """用 macOS sips + cupsfilter 把文本 PDF 变成真实扫描件（图像型）PDF。"""
    if shutil.which("sips") is None or shutil.which("cupsfilter") is None:
        pytest.skip("sips/cupsfilter not available")
    png = workdir / "scan-page.png"
    subprocess.run(
        [
            "sips",
            "-s",
            "format",
            "png",
            "--resampleWidth",
            "1700",
            str(source_pdf),
            "--out",
            str(png),
        ],
        check=True,
        capture_output=True,
    )
    scan = workdir / "scan-page.pdf"
    with scan.open("wb") as handle:
        subprocess.run(
            ["cupsfilter", "-i", "image/png", "-m", "application/pdf", str(png)],
            check=True,
            stdout=handle,
            stderr=subprocess.DEVNULL,
        )
    return scan


def test_real_native_pdf_never_calls_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "native.pdf"
    _build_simple_pdf(
        pdf,
        [
            ["NATIVE PAGE ONE MARKER", "Pure electronic text on the first page."],
            ["NATIVE PAGE TWO MARKER", "Pure electronic text on the second page."],
            ["NATIVE PAGE THREE MARKER", "Pure electronic text on the third page."],
        ],
    )

    mineru = Mock()
    adapter = SmartPdfAdapter(mineru=mineru)

    doc = adapter.prepare(pdf)

    mineru.prepare.assert_not_called()
    mineru.prepare_page.assert_not_called()
    assert doc.metadata["adapter"] == "smart_pdf"
    assert doc.metadata["parser_route"] == "native_only"
    assert "NATIVE PAGE ONE MARKER" in doc.text
    assert "NATIVE PAGE THREE MARKER" in doc.text
    assert doc.text.index("ONE") < doc.text.index("THREE")

    rows = doc.sidecars["page-routing.jsonl"].splitlines()
    assert len(rows) == 3
    assert all('"parser":"pdf_inspector"' in row for row in rows)


def _build_white_scan_source(path: Path) -> None:
    """单页白底大字文本 PDF，供栅格化成扫描件。

    PDF 页默认透明；sips 栅格化时不会像阅读器一样铺白底，
    必须显式画白底矩形，否则得到全黑图、OCR 输出为空。
    """

    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    lines = ["DOCCHUNK SCAN TEST PAGE", "This page is rasterized into a real scan."]
    parts = ["1 1 1 rg 0 0 612 792 re f", "0 0 0 rg", "BT /F1 28 Tf 72 660 Td 40 TL"]
    parts.extend(f"({escape(line)}) Tj T*" for line in lines)
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

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


def test_real_scanned_page_goes_through_mineru_prepare_page(tmp_path: Path) -> None:
    _mineru_or_skip()

    text_pdf = tmp_path / "scan-source.pdf"
    _build_white_scan_source(text_pdf)
    scan = _rasterize_to_scan_pdf(text_pdf, tmp_path)

    bundle = PdfInspectorAdapter().inspect_and_extract(scan)
    assert bundle.summary.page_count == 1
    assert bundle.pages[0].needs_ocr is True

    doc = MinerUAdapter().prepare_page(scan, 0)

    assert doc.metadata["page_mode"] is True
    assert doc.metadata["source_page_idx"] == 0
    assert all(block.page_idx == 0 for block in doc.blocks)
    assert doc.text.strip() != "", "MinerU OCR of a real scan page must produce text"
    assert "SCAN" in doc.text.upper(), f"OCR text should contain the marker: {doc.text!r}"


def test_real_mixed_pdf_keeps_page_order_and_routing(tmp_path: Path) -> None:
    _mineru_or_skip()

    pdf = tmp_path / "mixed.pdf"
    _build_mixed_pdf(pdf)

    bundle = PdfInspectorAdapter().inspect_and_extract(pdf)
    assert [page.needs_ocr for page in bundle.pages] == [False, True, False]

    doc = SmartPdfAdapter().prepare(pdf)

    assert doc.metadata["parser_route"] == "mixed"
    rows = doc.sidecars["page-routing.jsonl"].splitlines()
    assert len(rows) == 3
    assert '"parser":"pdf_inspector"' in rows[0]
    assert '"parser":"mineru"' in rows[1]
    assert '"parser":"pdf_inspector"' in rows[2]
    assert '"page_idx":0' in rows[0] and '"page_idx":1' in rows[1] and '"page_idx":2' in rows[2]

    assert "MIXED PAGE ONE MARKER" in doc.text
    assert "MIXED PAGE THREE MARKER" in doc.text
    assert doc.text.index("ONE MARKER") < doc.text.index("THREE MARKER")
    # 第 1、3 页 provenance 正确（第 2 页为图像无正文时允许无 block）
    native_pages = {block.page_idx for block in doc.blocks}
    assert native_pages <= {0, 1, 2}
    assert 0 in native_pages and 2 in native_pages


def _scan_image_stream(width: int = 300, height: int = 400) -> bytes:
    """White page with a black square in the middle (image-only, no text layer)."""
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            inside = (
                abs(x - width // 2) < width // 5 and abs(y - height // 2) < height // 5
            )
            row += b"\x00\x00\x00" if inside else b"\xff\xff\xff"
        rows.append(bytes(row))
    return zlib.compress(b"".join(rows))


def _build_mixed_pdf(path: Path) -> None:
    """3 页 PDF：第 1/3 页为原生文字，第 2 页为纯图像（无文字层）。"""

    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    image = _scan_image_stream()
    image_stream = (
        f"<< /Type /XObject /Subtype /Image /Width 300 /Height 400 "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
        f"/Length {len(image)} >>\nstream\n".encode()
        + image
        + b"\nendstream"
    )

    def text_page_stream(lines: list[str]) -> bytes:
        parts = ["BT /F1 14 Tf 72 700 Td 24 TL"]
        parts.extend(f"({escape(line)}) Tj T*" for line in lines)
        parts.append("ET")
        content = "\n".join(parts).encode("latin-1")
        return f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"

    page1 = text_page_stream(["MIXED PAGE ONE MARKER", "Native electronic text."])
    page2 = b"q 300 0 0 400 0 0 cm /Im1 Do Q"
    content2 = f"<< /Length {len(page2)} >>\nstream\n".encode() + page2 + b"\nendstream"
    page3 = text_page_stream(["MIXED PAGE THREE MARKER", "Native electronic text again."])

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 9 0 R >> >> /Contents 4 0 R >>"
        ),
        page1,  # content 1
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] "
            b"/Resources << /XObject << /Im1 10 0 R >> >> /Contents 6 0 R >>"
        ),
        content2,  # content 2
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 9 0 R >> >> /Contents 8 0 R >>"
        ),
        page3,  # content 3
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        image_stream,
    ]

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
