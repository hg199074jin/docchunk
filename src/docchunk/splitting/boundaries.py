import re

from pydantic import BaseModel

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


class HeadingMark(BaseModel):
    char_offset: int
    level: int
    title: str


def extract_heading_marks(text: str) -> list[HeadingMark]:
    return [
        HeadingMark(
            char_offset=match.start(),
            level=len(match.group(1)),
            title=match.group(2).strip(),
        )
        for match in HEADING_RE.finditer(text)
    ]


def heading_path_at(marks: list[HeadingMark], char_offset: int) -> list[str]:
    stack: list[HeadingMark] = []

    for mark in marks:
        if mark.char_offset > char_offset:
            break

        while stack and stack[-1].level >= mark.level:
            stack.pop()
        stack.append(mark)

    return [item.title for item in stack]
