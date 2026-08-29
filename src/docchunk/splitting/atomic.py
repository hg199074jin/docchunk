from pydantic import BaseModel
from semantic_text_splitter import MarkdownSplitter, TextSplitter

from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.boundaries import extract_heading_marks, heading_path_at
from docchunk.splitting.structured_blocks import find_markdown_tables, table_context_for_span
from docchunk.tokenizer import TokenCounter


class AtomicChunk(BaseModel):
    sequence: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    heading_path: list[str]
    forced_split: bool = False
    split_table: bool = False
    table_header_context: str | None = None


def _looks_like_forced_boundary(text: str, end: int) -> bool:
    if end <= 0 or end >= len(text):
        return False

    left = text[end - 1]
    right = text[end]

    natural_right = left in "。！？!?；;\n\r\t "
    natural_left = right in "\n\r\t #|"

    return not natural_right and not natural_left


def split_atomic(
    text: str,
    counter: TokenCounter,
    policy: AtomicPolicy,
    markdown: bool,
) -> list[AtomicChunk]:
    if not text:
        return []

    splitter_type = MarkdownSplitter if markdown else TextSplitter

    # 目标值作为 range 下界，soft_max 作为上界：
    # 尽量形成接近 6K 的块；遇到更高语义边界时允许更短。
    splitter = splitter_type.from_callback(
        counter.count,
        (policy.target_tokens, policy.soft_max_tokens),
        overlap=0,
        trim=False,
    )

    raw_chunks = splitter.chunk_indices(text)
    marks = extract_heading_marks(text) if markdown else []
    tables = find_markdown_tables(text) if markdown else []

    chunks: list[AtomicChunk] = []
    for sequence, (char_start, chunk_text) in enumerate(raw_chunks, start=1):
        char_end = char_start + len(chunk_text)
        split_table, table_header_context = table_context_for_span(
            tables,
            char_start,
            char_end,
        )
        chunks.append(
            AtomicChunk(
                sequence=sequence,
                text=chunk_text,
                token_count=counter.count(chunk_text),
                char_start=char_start,
                char_end=char_end,
                heading_path=heading_path_at(marks, char_start),
                forced_split=_looks_like_forced_boundary(text, char_end),
                split_table=split_table,
                table_header_context=table_header_context,
            )
        )

    if "".join(chunk.text for chunk in chunks) != text:
        raise ValueError("Atomic splitter changed normalized source text")

    return chunks
