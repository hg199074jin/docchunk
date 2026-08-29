from docchunk.batching.builder import build_batches
from docchunk.models.manifest import BatchPolicy
from docchunk.tokenizer import TokenCounter


def test_batches_overlap_by_whole_atomic_id() -> None:
    atomic_texts = {
        "A000001": "第一段。" * 20,
        "A000002": "第二段。" * 20,
        "A000003": "第三段。" * 20,
        "A000004": "第四段。" * 20,
    }
    policy = BatchPolicy(
        target_tokens=80,
        soft_min_tokens=40,
        soft_max_tokens=100,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    assert len(batches) >= 2
    assert batches[1].overlap_atomic_ids == [batches[0].atomic_ids[-1]]
    assert batches[1].atomic_ids[0] == batches[0].atomic_ids[-1]


def test_new_atomic_ids_cover_source_once() -> None:
    atomic_texts = {f"A{i:06d}": f"内容{i}。" * 10 for i in range(1, 8)}
    policy = BatchPolicy(
        target_tokens=60,
        soft_min_tokens=30,
        soft_max_tokens=80,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    new_ids = [item for batch in batches for item in batch.new_atomic_ids]
    assert new_ids == list(atomic_texts)


def test_table_header_context_is_marked_as_synthetic() -> None:
    atomic_texts = {
        "A000001": "| A | B |\n| --- | --- |\n| row1 | value1 |\n",
        "A000002": "| row2 | value2 |\n",
    }
    contexts = {
        "A000002": {
            "table_header": "| A | B |\n| --- | --- |\n",
        }
    }
    policy = BatchPolicy(
        target_tokens=200,
        soft_min_tokens=100,
        soft_max_tokens=240,
        overlap_atomic_count=0,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
        atomic_contexts=contexts,
    )

    assert "Synthetic Table Context" in batches[0].text
    assert "不是新的原文" in batches[0].text
    assert atomic_texts["A000002"] in batches[0].text


def test_overlap_atomic_is_not_repeated_as_new_material() -> None:
    atomic_texts = {f"A{i:06d}": ("正文。" * 20) for i in range(1, 6)}
    policy = BatchPolicy(
        target_tokens=50,
        soft_min_tokens=25,
        soft_max_tokens=70,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    for batch in batches[1:]:
        assert set(batch.overlap_atomic_ids).isdisjoint(batch.new_atomic_ids)
