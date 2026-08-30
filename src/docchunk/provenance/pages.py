from docchunk.adapters.base import NormalizedBlock
from docchunk.models.pdf import page_index_to_number


def source_pages_for_span(
    blocks: list[NormalizedBlock],
    char_start: int,
    char_end: int,
) -> tuple[int | None, int | None]:
    page_indexes = [
        block.page_idx
        for block in blocks
        if block.page_idx is not None
        and block.char_start < char_end
        and block.char_end > char_start
    ]

    if not page_indexes:
        return None, None

    return page_index_to_number(min(page_indexes)), page_index_to_number(max(page_indexes))
