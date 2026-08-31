from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class NormalizedBlock(BaseModel):
    block_index: int
    char_start: int
    char_end: int
    text: str
    page_idx: int | None = None
    heading_level: int | None = None
    bbox: list[float] | None = None


class NormalizedDocument(BaseModel):
    source_path: Path
    media_type: str
    text: str
    blocks: list[NormalizedBlock] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    # 逐页证据等辅助产物（如 page-routing.jsonl）：内容由 adapter 生成，
    # 落盘位置由 pipeline 决定，因此这里只携带「文件名 -> 文本内容」。
    sidecars: dict[str, str] = Field(default_factory=dict)


class DocumentAdapter(ABC):
    @abstractmethod
    def prepare(self, path: Path) -> NormalizedDocument:
        raise NotImplementedError


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
