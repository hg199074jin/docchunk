from docchunk.adapters.base import NormalizedBlock


def parse_content_list(content: list[dict[str, object]]) -> list[NormalizedBlock]:
    blocks: list[NormalizedBlock] = []

    for index, item in enumerate(content):
        raw_text = item.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue

        raw_page = item.get("page_idx")
        page_idx = raw_page if isinstance(raw_page, int) else None

        raw_level = item.get("text_level")
        heading_level = raw_level if isinstance(raw_level, int) else None

        raw_bbox = item.get("bbox")
        bbox = (
            [float(value) for value in raw_bbox]
            if isinstance(raw_bbox, list) and len(raw_bbox) == 4
            else None
        )

        # 此时还不知道它在 MinerU Markdown 中的真实 offset；
        # 由 align_blocks_to_markdown 重新对齐。
        blocks.append(
            NormalizedBlock(
                block_index=index,
                char_start=0,
                char_end=0,
                text=raw_text.strip(),
                page_idx=page_idx,
                heading_level=heading_level,
                bbox=bbox,
            )
        )

    return blocks


def align_blocks_to_markdown(
    markdown: str,
    blocks: list[NormalizedBlock],
) -> list[NormalizedBlock]:
    aligned: list[NormalizedBlock] = []
    search_cursor = 0

    for block in blocks:
        position = markdown.find(block.text, search_cursor)
        if position < 0:
            # OCR/Markdown 渲染可能让极少数 block 找不到；
            # 不伪造 offset，直接跳过未对齐 block，
            # Adapter metadata 负责记录未对齐数量。
            continue

        end = position + len(block.text)
        aligned.append(
            block.model_copy(
                update={
                    "char_start": position,
                    "char_end": end,
                }
            )
        )
        search_cursor = end

    return aligned


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

    # MinerU 0-based → 用户可读 1-based。
    return min(page_indexes) + 1, max(page_indexes) + 1
