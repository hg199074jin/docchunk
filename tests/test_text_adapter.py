from docchunk.adapters.text import TextAdapter


def test_text_adapter_preserves_paragraphs(tmp_path) -> None:
    source = tmp_path / "course.txt"
    source.write_text("第一段。\n\n第二段。", encoding="utf-8")

    doc = TextAdapter().prepare(source)

    assert doc.text == "第一段。\n\n第二段。"
    assert doc.media_type == "text/plain"
