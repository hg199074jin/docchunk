from pydantic import BaseModel

from docchunk.models.manifest import BatchPolicy
from docchunk.tokenizer import TokenCounter


class ReadingBatch(BaseModel):
    batch_id: str
    atomic_ids: list[str]
    overlap_atomic_ids: list[str]
    new_atomic_ids: list[str]
    token_count: int
    text: str


def _render_atomic(
    atomic_id: str,
    text: str,
    context: dict[str, str],
) -> list[str]:
    lines = [f"## {atomic_id}", ""]

    table_header = context.get("table_header")
    if table_header:
        lines.extend(
            [
                "### Synthetic Table Context",
                "",
                "> 以下表头仅用于帮助理解跨 Atomic 表格，属于上下文提示，不是新的原文。",
                "",
                table_header.rstrip("\n"),
                "",
            ]
        )

    lines.extend([text, ""])
    return lines


def _render_batch(
    batch_id: str,
    overlap_ids: list[str],
    new_ids: list[str],
    atomic_texts: dict[str, str],
    contexts: dict[str, dict[str, str]],
) -> str:
    lines = [
        "---",
        f"batch_id: {batch_id}",
        "overlap_atomic_ids:",
    ]

    if overlap_ids:
        lines.extend(f"  - {item}" for item in overlap_ids)
    else:
        lines.append("  []")

    lines.append("new_atomic_ids:")
    lines.extend(f"  - {item}" for item in new_ids)
    lines.extend(["---", ""])

    if overlap_ids:
        lines.extend(
            [
                "# Context Bridge",
                "",
                (
                    "> 以下 Atomic 已在上一批读取，仅用于保持上下文连续性；"
                    "下游提取器不得把它们当作新的证据再次计入。"
                ),
                "",
            ]
        )
        for item in overlap_ids:
            lines.extend(
                _render_atomic(
                    item,
                    atomic_texts[item],
                    contexts.get(item, {}),
                )
            )

    lines.extend(["# New Material", ""])
    for item in new_ids:
        lines.extend(
            _render_atomic(
                item,
                atomic_texts[item],
                contexts.get(item, {}),
            )
        )

    return "\n".join(lines)


def build_batches(
    atomic_texts: dict[str, str],
    counter: TokenCounter,
    policy: BatchPolicy,
    atomic_contexts: dict[str, dict[str, str]] | None = None,
) -> list[ReadingBatch]:
    contexts = atomic_contexts or {}
    ordered_ids = list(atomic_texts)
    batches: list[ReadingBatch] = []
    cursor = 0
    previous_new_ids: list[str] = []

    while cursor < len(ordered_ids):
        overlap_ids = (
            previous_new_ids[-policy.overlap_atomic_count :]
            if batches and policy.overlap_atomic_count > 0
            else []
        )
        selected = list(overlap_ids)
        new_ids: list[str] = []

        while cursor < len(ordered_ids):
            atomic_id = ordered_ids[cursor]
            candidate_new_ids = new_ids + [atomic_id]
            candidate_rendered = _render_batch(
                batch_id=f"B{len(batches) + 1:04d}",
                overlap_ids=overlap_ids,
                new_ids=candidate_new_ids,
                atomic_texts=atomic_texts,
                contexts=contexts,
            )
            candidate_tokens = counter.count(candidate_rendered)

            if new_ids and candidate_tokens > policy.target_tokens:
                break

            selected.append(atomic_id)
            new_ids.append(atomic_id)
            cursor += 1

            if candidate_tokens >= policy.soft_max_tokens:
                break

        if not new_ids and cursor < len(ordered_ids):
            atomic_id = ordered_ids[cursor]
            selected.append(atomic_id)
            new_ids.append(atomic_id)
            cursor += 1

        batch_id = f"B{len(batches) + 1:04d}"
        rendered = _render_batch(
            batch_id=batch_id,
            overlap_ids=overlap_ids,
            new_ids=new_ids,
            atomic_texts=atomic_texts,
            contexts=contexts,
        )

        batches.append(
            ReadingBatch(
                batch_id=batch_id,
                atomic_ids=selected,
                overlap_atomic_ids=overlap_ids,
                new_atomic_ids=new_ids,
                token_count=counter.count(rendered),
                text=rendered,
            )
        )
        previous_new_ids = new_ids

    return batches
