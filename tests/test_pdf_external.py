from pathlib import Path
from unittest.mock import patch

import pytest

from docchunk.adapters.pdf import SmartPdfAdapter
from docchunk.adapters.pdf_inspector import PdfInspectorAdapter


def _build_native_pdf(path: Path) -> None:
    stream = b"BT /F1 12 Tf 72 720 Td (Native PDF smoke test) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(output)


@pytest.mark.external
def test_native_pdf_uses_inspector_without_mineru(tmp_path: Path) -> None:
    pdf = tmp_path / "native.pdf"
    _build_native_pdf(pdf)

    bundle = PdfInspectorAdapter().inspect_and_extract(pdf)
    assert bundle.summary.page_count == 1
    assert bundle.pages[0].needs_ocr is False

    adapter = SmartPdfAdapter()
    with patch.object(adapter.mineru, "prepare_page") as prepare_page, patch.object(
        adapter.inspector, "inspect_and_extract", return_value=bundle
    ):
        document = adapter.prepare(pdf)

    prepare_page.assert_not_called()
    assert document.metadata["parser_route"] == "native_only"
