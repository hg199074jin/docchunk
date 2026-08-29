from pathlib import Path

from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.atomic import split_atomic
from docchunk.splitting.structured_blocks import find_markdown_tables
from docchunk.tokenizer import TokenCounter


def test_table_span_and_header_are_detected() -> None:
    text = Path("tests/fixtures/tables.md").read_text(encoding="utf-8")
    tables = find_markdown_tables(text)

    assert len(tables) == 1
    assert tables[0].header == "| 姓名 | 金额 |\n| --- | ---: |\n"
    assert text[tables[0].char_start:tables[0].char_end].startswith("| 姓名 |")


def test_table_context_never_changes_atomic_source_text() -> None:
    text = (
        "# 表\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        + "".join(f"| row{i} | value{i} |\n" for i in range(200))
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=80,
            soft_min_tokens=40,
            soft_max_tokens=110,
        ),
        markdown=True,
    )

    assert "".join(chunk.text for chunk in chunks) == text
    assert any(chunk.table_header_context for chunk in chunks[1:])


def test_small_fenced_code_block_remains_inside_one_chunk() -> None:
    text = (
        "# 示例\n\n"
        "前文。\n\n"
        "```python\n"
        "print('x')\n"
        "print('y')\n"
        "```\n\n"
        "后文。\n"
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=200,
            soft_min_tokens=100,
            soft_max_tokens=260,
        ),
        markdown=True,
    )

    matching = [chunk for chunk in chunks if "print('x')" in chunk.text]
    assert len(matching) == 1
    assert "print('y')" in matching[0].text
