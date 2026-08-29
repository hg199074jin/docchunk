from pydantic import BaseModel, Field


class AtomicFlags(BaseModel):
    forced_split: bool = False
    split_table: bool = False
    adapter_fallback: bool = False


class SourceLocation(BaseModel):
    file: str
    page_start: int | None = None
    page_end: int | None = None
    block_start: int | None = None
    block_end: int | None = None


class AtomicIndexRecord(BaseModel):
    atomic_id: str
    document_id: str
    sequence: int
    path: str
    token_count: int = Field(ge=0)
    # char_start/char_end 始终是“该 document 的 normalized Markdown”内的字符坐标，
    # 不是整个多文件 Corpus 的全局字符坐标。
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    heading_path: list[str] = Field(default_factory=list)
    source: SourceLocation
    flags: AtomicFlags = Field(default_factory=AtomicFlags)
    context: dict[str, str] = Field(default_factory=dict)
