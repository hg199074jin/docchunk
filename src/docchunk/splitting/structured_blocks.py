import re

from pydantic import BaseModel

TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


class MarkdownTable(BaseModel):
    char_start: int
    char_end: int
    header: str


def find_markdown_tables(text: str) -> list[MarkdownTable]:
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0

    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    tables: list[MarkdownTable] = []
    index = 0

    while index + 1 < len(lines):
        header_line = lines[index]
        separator_line = lines[index + 1]

        if "|" not in header_line or not TABLE_SEPARATOR_RE.match(separator_line.rstrip("\n")):
            index += 1
            continue

        start_index = index
        index += 2

        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            index += 1

        start = offsets[start_index]
        end = offsets[index] if index < len(lines) else len(text)
        tables.append(
            MarkdownTable(
                char_start=start,
                char_end=end,
                header=header_line + separator_line,
            )
        )

    return tables


def table_context_for_span(
    tables: list[MarkdownTable],
    char_start: int,
    char_end: int,
) -> tuple[bool, str | None]:
    for table in tables:
        overlaps = table.char_start < char_end and table.char_end > char_start
        if not overlaps:
            continue

        begins_after_header = char_start > table.char_start + len(table.header)
        return True, table.header if begins_after_header else None

    return False, None
