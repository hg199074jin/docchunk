from itertools import pairwise

from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.atomic import split_atomic
from docchunk.tokenizer import TokenCounter


def test_short_text_remains_one_atomic_chunk() -> None:
    text = "# 第一章\n\n第一段。\n\n第二段。"
    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=6000,
            soft_min_tokens=4000,
            soft_max_tokens=8000,
        ),
        markdown=True,
    )

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_long_chinese_text_is_lossless() -> None:
    text = (
        "# 第一节\n\n"
        + "这是第一段。这里继续解释第一段的概念。" * 40
        + "\n\n"
        + "这是第二段。这里继续给出第二段的案例。" * 40
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

    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == text


def test_atomic_offsets_are_contiguous() -> None:
    text = ("第一段。" * 80) + "\n\n" + ("第二段。" * 80)

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=60,
            soft_min_tokens=30,
            soft_max_tokens=90,
        ),
        markdown=False,
    )

    assert chunks[0].char_start == 0
    for previous, current in pairwise(chunks):
        assert previous.char_end == current.char_start
    assert chunks[-1].char_end == len(text)


def test_heading_path_follows_markdown_structure() -> None:
    text = (
        "# 第一章\n\n"
        "开头。\n\n"
        "## 第二节\n\n"
        + ("这一节内容。" * 100)
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=40,
            soft_min_tokens=20,
            soft_max_tokens=60,
        ),
        markdown=True,
    )

    second_section = [chunk for chunk in chunks if "这一节内容" in chunk.text]
    assert second_section
    assert second_section[0].heading_path == ["第一章", "第二节"]


def test_atomic_chunks_respect_soft_max_except_diagnostic_cases() -> None:
    text = "这是一个完整句子。" * 300

    policy = AtomicPolicy(
        target_tokens=50,
        soft_min_tokens=30,
        soft_max_tokens=70,
    )
    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=policy,
        markdown=False,
    )

    assert all(chunk.token_count <= policy.soft_max_tokens for chunk in chunks)
