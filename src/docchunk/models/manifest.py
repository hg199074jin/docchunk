from datetime import UTC, datetime

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TokenizerConfig(BaseModel):
    provider: str = "tiktoken"
    encoding: str = "o200k_base"


class AtomicPolicy(BaseModel):
    target_tokens: int = 6000
    soft_min_tokens: int = 4000
    soft_max_tokens: int = 8000


class BatchPolicy(BaseModel):
    target_tokens: int = 24000
    soft_min_tokens: int = 16000
    soft_max_tokens: int = 32000
    overlap_atomic_count: int = 1


class CorpusCounts(BaseModel):
    documents: int = 0
    atomic_chunks: int = 0
    reading_batches: int = 0
    normalized_tokens: int = 0


class VerificationInfo(BaseModel):
    status: str = "pending"
    checked_at: str | None = None
    errors: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    schema_version: str = "1.0"
    corpus_id: str
    title: str
    source_type: str
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    tokenizer: TokenizerConfig = Field(default_factory=TokenizerConfig)
    atomic_policy: AtomicPolicy = Field(default_factory=AtomicPolicy)
    batch_policy: BatchPolicy = Field(default_factory=BatchPolicy)
    documents: list[dict[str, object]] = Field(default_factory=list)
    normalization: dict[str, object] = Field(default_factory=dict)
    counts: CorpusCounts = Field(default_factory=CorpusCounts)
    verification: VerificationInfo = Field(default_factory=VerificationInfo)
