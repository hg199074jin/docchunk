from enum import StrEnum

from pydantic import BaseModel, Field


class ProcessingStage(StrEnum):
    NEW = "new"
    PREPARING = "preparing"
    PREPARED = "prepared"
    SPLITTING = "splitting"
    SPLIT = "split"
    BATCHING = "batching"
    BATCHED = "batched"
    VERIFYING = "verifying"
    READY = "ready"
    FAILED = "failed"


class CorpusState(BaseModel):
    stage: ProcessingStage = ProcessingStage.NEW
    current_document_id: str | None = None
    current_batch_id: str | None = None
    completed_batches: list[str] = Field(default_factory=list)
    failed_batch: str | None = None
    error: str | None = None
