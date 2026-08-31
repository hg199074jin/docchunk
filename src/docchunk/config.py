import shutil
from pathlib import Path

from pydantic import BaseModel, Field

_MINERU_VENV_FALLBACK = Path.home() / ".venvs" / "mineru" / "bin" / "mineru"

# Smart PDF 路由策略版本：变化会改变 normalized Markdown，
# 因此进入 normalization fingerprint，旧缓存自动失效（设计 §41）。
PAGE_SMART_PDF_POLICY_VERSION = "page_smart_v1"


def resolve_mineru_command(configured: str = "mineru") -> str:
    if configured != "mineru":
        return configured

    found = shutil.which("mineru")
    if found:
        return found

    # 本机（2026-08-29 核实）：MinerU 3.4.5 在专用 venv，不在系统 PATH。
    if _MINERU_VENV_FALLBACK.exists():
        return str(_MINERU_VENV_FALLBACK)

    return configured


class AppConfig(BaseModel):
    corpus_root: Path = Path("/Volumes/ORICO/LongDocCorpus")
    tokenizer_encoding: str = "o200k_base"
    atomic_target_tokens: int = Field(default=6000, gt=0)
    atomic_soft_min_tokens: int = Field(default=4000, gt=0)
    atomic_soft_max_tokens: int = Field(default=8000, gt=0)
    batch_target_tokens: int = Field(default=24000, gt=0)
    batch_soft_min_tokens: int = Field(default=16000, gt=0)
    batch_soft_max_tokens: int = Field(default=32000, gt=0)
    overlap_atomic_count: int = Field(default=1, ge=0)
    hard_context_limit: int = Field(default=256000, gt=0)
    mineru_command: str = "mineru"
    mineru_backend: str = "hybrid-engine"
    mineru_effort: str = "medium"
    docx_fallback_to_mineru: bool = False
    verbose: bool = False
