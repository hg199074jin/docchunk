from docchunk.adapters.markdown import MarkdownAdapter


def test_markdown_adapter_normalizes_line_endings(tmp_path) -> None:
    source = tmp_path / "book.md"
    source.write_bytes("# 第一章\r\n\r\n第一段。\r\n".encode())

    doc = MarkdownAdapter().prepare(source)

    assert doc.text == "# 第一章\n\n第一段。\n"
    assert doc.source_path == source
    assert doc.media_type == "text/markdown"
