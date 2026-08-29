# docchunk + longdoc-router V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地优先、可验证、可断点续跑的长文档预处理 CLI `docchunk`，并提供 `longdoc-router` Skill，把书籍、课程逐字稿和资料集稳定地分批交给 Cangjie/Nuwa 等成熟蒸馏 Skill，再按需交给 `personal-capability-distiller` 做长期能力沉淀。

**Architecture:** `docchunk` 只负责确定性的数据处理：输入适配 → 标准化 → 无损 Atomic Chunk → Reading Batch → provenance/index/manifest → verify/state。`longdoc-router` 是独立的 Agent 编排层，只读取 Corpus 契约、顺序调度 Batch，并路由到第三方 Skill；它不修改 Cangjie、Nuwa 或 `personal-capability-distiller` 的源码。

**Tech Stack:** Python 3.12、uv、Typer、Pydantic v2、tiktoken、semantic-text-splitter、Rich、pytest、pytest-cov、Ruff、mypy；外部 CLI：MinerU、Pandoc；Git/GitHub。

**Spec:** `docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md`

## Global Constraints

- Python 固定使用 3.12；不要在 V1 中同时支持多个 Python 大版本。
- `docchunk` 本身不得调用任何 LLM API，不上传用户原始资料。
- PDF 默认 MinerU First；DOCX 默认 Pandoc First，失败时才允许显式 MinerU fallback。
- Markdown/TXT 直接处理，不经过 LLM。
- Atomic Chunk 默认 target 6000 tokens、soft range 4000–8000、无 overlap。
- Reading Batch 默认 target 24000 tokens、soft range 16000–32000、默认 overlap 1 个完整 Atomic Chunk。
- 默认 hard context profile 为 256000 tokens，但绝不能把 256K 当默认 Batch 大小。
- Atomic Chunk 必须保持顺序、不得无意重复、不得无意缺失。
- Reading Batch 的 overlap 只能由完整 Atomic Chunk 构成。
- 原始文件永不覆盖；所有生成物写入 Corpus 目录。
- 所有 fallback、forced split、OCR/转换异常必须显式记录，禁止静默处理。
- Corpus 数据格式必须与 Codex、Cangjie、Nuwa 解耦。
- 不修改、不 fork Cangjie、Nuwa、`personal-capability-distiller`。
- Corpus 与 Obsidian 物理分离；Obsidian 只保存来源指针和能力资产。
- V1 不实现 GUI、RAG、向量库、LLM semantic chunking、自动摘要、自动去口语、自动 ASR。
- 开发顺序严格采用测试驱动：先写失败测试，再写最小实现，再运行测试，再提交。
- 每个 Task 完成后必须独立可测试，并形成一个 Git commit。
- 实施过程中若设计与本计划冲突，以已批准的设计文档为准；若必须改变设计，先停止实现并更新设计文档。

---

# 0. 给第一次做项目的人看的执行方法

## 0.1 不要一次把整份计划交给 Agent 后让它“全部做完”

正确方式：

1. 创建仓库。
2. 把设计文档和本实施计划放进仓库。
3. 让 Agent 读取两个文档。
4. 一次只执行一个 Task。
5. 每个 Task 完成后先跑测试。
6. 测试全部通过再提交 Git。
7. 再进入下一个 Task。

推荐给 Agent 的固定指令：

```text
请先阅读：
1. docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md
2. docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md

现在只执行 Task N。
严格测试驱动：先写失败测试，确认失败，再写最小实现，确认测试通过。
不要提前执行后续 Task。
完成后告诉我：
- 修改了哪些文件
- 执行了哪些测试
- 测试结果
- Git commit SHA
- 是否存在偏离设计的地方
```

## 0.2 每次看到测试失败，不要直接跳过

测试失败只有三种处理：

- 实现有 bug：修代码；
- 测试写错：说明为什么测试与设计不一致，再修测试；
- 环境缺依赖：先修环境。

绝不能通过删除测试、`skip` 测试或降低断言来“让它变绿”。

## 0.3 本计划所有路径均相对于仓库根目录

仓库根目录（2026-08-29 确认）：

```text
/Volumes/ORICO/Projects/docchunk/
```

外接盘为 APFS 格式，git / venv / 符号链接均无兼容性问题。如果仓库日后迁移到其他目录，内部相对路径仍保持不变。

---

# 1. 最终文件结构

实施完成后，仓库应至少具有以下结构：

```text
docchunk/
├── .gitignore
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── docs/
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-08-29-docchunk-longdoc-router-design.md
│       └── plans/
│           └── 2026-08-29-docchunk-longdoc-router-v1.md
├── src/
│   └── docchunk/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── errors.py
│       ├── logging_utils.py
│       ├── fingerprints.py
│       ├── tokenizer.py
│       ├── inspect_input.py
│       ├── pipeline.py
│       ├── storage.py
│       ├── verify.py
│       ├── doctor.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── source.py
│       │   ├── manifest.py
│       │   ├── index.py
│       │   └── state.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── markdown.py
│       │   ├── text.py
│       │   ├── pandoc.py
│       │   ├── mineru.py
│       │   └── directory.py
│       ├── splitting/
│       │   ├── __init__.py
│       │   ├── boundaries.py
│       │   ├── atomic.py
│       │   └── structured_blocks.py
│       ├── batching/
│       │   ├── __init__.py
│       │   └── builder.py
│       └── provenance/
│           ├── __init__.py
│           └── mineru.py
├── skills/
│   └── longdoc-router/
│       ├── SKILL.md
│       └── references/
│           ├── routing.md
│           ├── corpus-contract.md
│           ├── cangjie-adapter.md
│           ├── nuwa-adapter.md
│           ├── personal-capability-adapter.md
│           └── resume.md
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── sample.md
    │   ├── sample.txt
    │   ├── transcript-zh.txt
    │   ├── tables.md
    │   ├── mineru-content-list.json
    │   └── mineru-normalized.md
    ├── test_cli_smoke.py
    ├── test_models.py
    ├── test_tokenizer.py
    ├── test_markdown_adapter.py
    ├── test_text_adapter.py
    ├── test_pandoc_adapter.py
    ├── test_mineru_adapter.py
    ├── test_directory_adapter.py
    ├── test_atomic_splitter.py
    ├── test_structured_blocks.py
    ├── test_storage.py
    ├── test_batch_builder.py
    ├── test_pipeline.py
    ├── test_verify.py
    ├── test_state_resume.py
    ├── test_doctor.py
    └── test_integration_corpus.py
```

设计要求：每个文件只负责一个明确职责，不允许把所有逻辑堆进 `cli.py`。

---

# Task 0：本机环境基线（2026-08-29 已核实，无需安装操作）

在开始 Task 1 前，以下事实已在目标机上核实完毕。执行 Agent **不需要**再安装任何东西；若实施日期与核实日期相距过久，先重新核对再开工。

| 项目 | 本机事实 | 对计划的影响 |
|---|---|---|
| 仓库根目录 | `/Volumes/ORICO/Projects/docchunk`（外接 APFS 盘，目录已存在，含 `doc/`） | Task 1 不再创建 `~/Projects` |
| Python | 3.12.14，uv 管理的默认 `python3` | `uv python install 3.12` 为 no-op，直接可用 |
| uv / git / gh | uv 0.12.5 / git 2.55 / gh 2.97.0（已登录 hg199074jin，git 协议 ssh） | Task 1 Step 16 使用 SSH URL |
| MinerU | 3.4.5 @ `~/.venvs/mineru/bin/mineru`，**不在 PATH**；默认 backend `hybrid-engine` + `--effort medium`；模型在 `/Volumes/ORICO/Data/mineru-models`；CLI 已核对：`-p/-o` 必填，无 `--source` 参数 | config 增加路径解析与 backend/effort 字段 |
| Pandoc | 3.11 @ `/usr/local/bin/pandoc`，官方 pkg，已在 PATH | 无待办；按 AGENTS.md 第 16 节禁止 brew 重装 |
| tiktoken 网络 | `openaipublic.blob.core.windows.net` 与 PyPI 经代理可达 | 首次运行下载 encoding 无障碍 |
| Corpus 根目录 | 默认 `/Volumes/ORICO/LongDocCorpus`（2026-08-29 确认） | config 默认值 |
| 硬件 | Apple M4（10 核）/ 24GB 统一内存 / 内置盘可用 372GB / ORICO 954GB APFS | hybrid medium 余量充足；V1 串行足够 |

纪律约束（沿袭 `~/.codex/AGENTS.md`）：不修改 `~/mineru.json`；不往 `~/.venvs/mineru` 安装任何包；MinerU/Pandoc 失败必须显式报告，禁止静默 fallback。

---

# Phase A — 先把 `docchunk` CLI 做成独立可用的软件

## Task 1: 初始化仓库、Python 3.12、CLI 空壳与质量工具

**目标：** 获得一个最小但正规的 Python CLI 项目：`uv run docchunk --help` 可运行，pytest/Ruff/mypy 都有统一入口，设计文档与实施计划进入版本控制。

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `LICENSE`
- Create: `src/docchunk/__init__.py`
- Create: `src/docchunk/__main__.py`
- Create: `src/docchunk/cli.py`
- Create: `tests/test_cli_smoke.py`
- Save approved spec as: `docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md`
- Save this implementation plan as: `docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md`

**Interfaces:**
- Produces CLI entrypoint: `docchunk`
- Produces package version constant: `docchunk.__version__`
- Later tasks import the Typer app from `docchunk.cli:app`

- [ ] **Step 1: 检查基础命令**

```bash
git --version
uv --version
gh --version
```

Expected: 三条命令都能打印版本号。

若 `uv` 不存在，本计划先停止，不要改用系统 `pip` 临时拼环境。先把 `uv` 安装好再继续。

- [ ] **Step 2: 在既有目录初始化 Git**

```bash
cd /Volumes/ORICO/Projects/docchunk
git init
mkdir -p src/docchunk tests docs/superpowers/specs docs/superpowers/plans
```

目录已存在（内含 `doc/` 下的两份原始文档），不要新建目录，也不要 `mkdir -p ~/Projects`。

Expected: 输出中包含 `Initialized empty Git repository`。

- [ ] **Step 3: 把已批准的设计稿和本实施方案放进仓库**

两份文档当前在 `doc/` 下，复制为规范路径（原件保留在 `doc/`，并加入 `.gitignore`，避免双份内容漂移）：

```bash
cp doc/docchunk-longdoc-router-v1-design.md \
   docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md
cp doc/docchunk-longdoc-router-v1-implementation-plan.md \
   docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md
```

执行：

```bash
test -s docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md
test -s docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md
printf 'design and plan files are present\n'
```

Expected:

```text
design and plan files are present
```

- [ ] **Step 4: 固定 Python 3.12**

```bash
uv python install 3.12
uv init --python 3.12 --bare
uv run python --version
```

Expected: `Python 3.12` 开头。

- [ ] **Step 5: 安装运行依赖**

```bash
uv add typer pydantic tiktoken semantic-text-splitter rich
```

- [ ] **Step 6: 安装开发依赖**

```bash
uv add --dev pytest pytest-cov ruff mypy
```

- [ ] **Step 7: 配置 `pyproject.toml`**

保留 `uv add` 已写入的 dependency 列表，在同一文件补充/确认以下配置：

```toml
[project]
name = "docchunk"
version = "0.1.0"
description = "Lossless, token-aware long-document preprocessing for LLM reading workflows"
requires-python = ">=3.12,<3.13"

[project.scripts]
docchunk = "docchunk.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["docchunk"]

[[tool.mypy.overrides]]
module = ["semantic_text_splitter"]
ignore_missing_imports = true
```

不要把 `uv` 已生成的 `[project.dependencies]` 或 dependency array 删掉。

- [ ] **Step 8: 写 `.gitignore`**

`.gitignore`:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.DS_Store
.env
.env.*
!.env.example

# 本地真实资料和 Corpus 永远不提交
LongDocCorpus/
corpora/
private-fixtures/

# 原始文档副本（规范副本在 docs/superpowers/ 下）
doc/
```

- [ ] **Step 9: 写 README 初始页**

`README.md`:

```markdown
# docchunk

Lossless, token-aware long-document preprocessing for reliable LLM reading.

V1 goals:

- PDF via MinerU
- DOCX via Pandoc
- Markdown/TXT direct
- lossless Atomic Chunks
- token-aware Reading Batches
- provenance + verification
- longdoc-router integration

The full user guide is completed in Task 22.
```

- [ ] **Step 10: 写 MIT LICENSE**

`LICENSE` 使用标准 MIT License，版权行写：

```text
Copyright (c) 2026 hg199074jin
```

其余正文使用标准 MIT License 原文。不要自创许可证条款。

- [ ] **Step 11: 先写失败的 CLI 测试**

`tests/test_cli_smoke.py`:

```python
from typer.testing import CliRunner

from docchunk.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Long-document preprocessing" in result.stdout
```

- [ ] **Step 12: 运行测试，确认先失败**

```bash
uv run pytest tests/test_cli_smoke.py -v
```

Expected: `ModuleNotFoundError` 或等价的 `docchunk.cli` 导入失败。

- [ ] **Step 13: 写最小 CLI**

`src/docchunk/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/docchunk/cli.py`:

```python
import typer

app = typer.Typer(
    name="docchunk",
    help="Long-document preprocessing for reliable LLM reading.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show docchunk version."""
    from docchunk import __version__

    typer.echo(__version__)
```

`src/docchunk/__main__.py`:

```python
from docchunk.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 14: 跑测试和质量检查**

```bash
uv run pytest tests/test_cli_smoke.py -v
uv run ruff check .
uv run mypy src
uv run docchunk --help
uv run docchunk version
```

Expected:
- pytest `1 passed`；
- Ruff exit 0；
- mypy exit 0；
- `docchunk version` 输出 `0.1.0`。

- [ ] **Step 15: 第一次 Git 提交**

```bash
git add .
git commit -m "chore: bootstrap docchunk project"
```

- [ ] **Step 16: 创建 GitHub 远程仓库**

先检查 GitHub CLI：

```bash
gh auth status
```

如果 `hg199074jin/docchunk` 尚未存在：

```bash
gh repo create hg199074jin/docchunk \
  --public \
  --source=. \
  --remote=origin \
  --push
```

如果仓库已经存在，则（本机 gh 的 git 协议为 ssh）：

```bash
git remote add origin git@github.com:hg199074jin/docchunk.git
git push -u origin main
```

若本地默认分支仍叫 `master`，先统一成 `main`：

```bash
git branch -M main
git push -u origin main
```

- [ ] **Step 17: Task 1 验收**

```bash
git status
git remote -v
uv run pytest
uv run ruff check .
uv run mypy src
```

Expected:
- Git 工作区 clean；
- `origin` 指向 `hg199074jin/docchunk`；
- 所有检查通过。

## Task 2: 定义 Corpus 的 Pydantic 数据契约

**目标：** 先把 Manifest、Atomic Index、Source、State 的字段固定下来，后续模块都只依赖这些模型。

**Files:**
- Create: `src/docchunk/models/__init__.py`
- Create: `src/docchunk/models/source.py`
- Create: `src/docchunk/models/manifest.py`
- Create: `src/docchunk/models/index.py`
- Create: `src/docchunk/models/state.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces `SourceRef`
- Produces `AtomicIndexRecord`
- Produces `Manifest`
- Produces `CorpusState`
- Produces `ProcessingStage`

- [ ] **Step 1: 写失败测试**

`tests/test_models.py`:

```python
from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.models.manifest import AtomicPolicy, BatchPolicy, Manifest, TokenizerConfig
from docchunk.models.state import CorpusState, ProcessingStage


def test_manifest_round_trip() -> None:
    manifest = Manifest(
        corpus_id="demo-abc123",
        title="Demo",
        source_type="file",
        tokenizer=TokenizerConfig(provider="tiktoken", encoding="o200k_base"),
        atomic_policy=AtomicPolicy(
            target_tokens=6000,
            soft_min_tokens=4000,
            soft_max_tokens=8000,
        ),
        batch_policy=BatchPolicy(
            target_tokens=24000,
            soft_min_tokens=16000,
            soft_max_tokens=32000,
            overlap_atomic_count=1,
        ),
    )

    restored = Manifest.model_validate_json(manifest.model_dump_json())
    assert restored.corpus_id == "demo-abc123"
    assert restored.atomic_policy.target_tokens == 6000


def test_atomic_record_keeps_provenance() -> None:
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=1234,
        char_start=0,
        char_end=100,
        heading_path=["第一章"],
        source=SourceLocation(
            file="book.pdf",
            page_start=1,
            page_end=2,
        ),
        flags=AtomicFlags(),
    )

    assert record.source.page_start == 1
    assert record.flags.forced_split is False


def test_state_defaults_to_new() -> None:
    state = CorpusState()
    assert state.stage is ProcessingStage.NEW
```

- [ ] **Step 2: 运行并确认失败**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `docchunk.models` 相关模块导入失败。

- [ ] **Step 3: 实现 `source.py`**

```python
from pathlib import Path

from pydantic import BaseModel


class SourceRef(BaseModel):
    path: str
    sha256: str
    media_type: str
    size_bytes: int

    @classmethod
    def from_path(cls, path: Path, sha256: str, media_type: str) -> "SourceRef":
        return cls(
            path=str(path),
            sha256=sha256,
            media_type=media_type,
            size_bytes=path.stat().st_size,
        )
```

- [ ] **Step 4: 实现 `index.py`**

```python
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
```

- [ ] **Step 5: 实现 `manifest.py`**

```python
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
```

- [ ] **Step 6: 实现 `state.py`**

```python
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
```

- [ ] **Step 7: 添加统一导出**

`src/docchunk/models/__init__.py`:

```python
from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.models.manifest import AtomicPolicy, BatchPolicy, Manifest, TokenizerConfig
from docchunk.models.source import SourceRef
from docchunk.models.state import CorpusState, ProcessingStage

__all__ = [
    "AtomicFlags",
    "AtomicIndexRecord",
    "AtomicPolicy",
    "BatchPolicy",
    "CorpusState",
    "Manifest",
    "ProcessingStage",
    "SourceLocation",
    "SourceRef",
    "TokenizerConfig",
]
```

- [ ] **Step 8: 跑测试和类型检查**

```bash
uv run pytest tests/test_models.py -v
uv run ruff check src tests
uv run mypy src
```

Expected: 全部通过。

- [ ] **Step 9: 提交**

```bash
git add src/docchunk/models tests/test_models.py
git commit -m "feat: define corpus data contracts"
```

---

## Task 3: SHA256、配置和 tokenizer 封装

**目标：** 所有 token 计数和 fingerprint 都经过一个统一模块，禁止后续代码到处直接调用 `tiktoken`。

**Files:**
- Create: `src/docchunk/config.py`
- Create: `src/docchunk/fingerprints.py`
- Create: `src/docchunk/tokenizer.py`
- Create: `tests/test_tokenizer.py`

**Interfaces:**
- Produces `AppConfig`
- Produces `sha256_file(path: Path) -> str`
- Produces `stable_fingerprint(data: object) -> str`
- Produces `TokenCounter.count(text: str) -> int`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path

from docchunk.fingerprints import sha256_file, sha256_text, stable_fingerprint
from docchunk.tokenizer import TokenCounter


def test_sha256_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("abc", encoding="utf-8")

    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_text_hashes_utf8_bytes() -> None:
    assert sha256_text("abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_fingerprint_ignores_dict_key_order() -> None:
    assert stable_fingerprint({"a": 1, "b": 2}) == stable_fingerprint({"b": 2, "a": 1})


def test_token_counter_counts_non_empty_text() -> None:
    counter = TokenCounter("o200k_base")
    assert counter.count("这是一个测试。") > 0
    assert counter.count("") == 0
```

- [ ] **Step 2: 确认失败**

```bash
uv run pytest tests/test_tokenizer.py -v
```

- [ ] **Step 3: 实现 fingerprint**

`src/docchunk/fingerprints.py`:

```python
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_fingerprint(data: Any) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: 实现 tokenizer**

`src/docchunk/tokenizer.py`:

```python
import tiktoken


class TokenCounter:
    def __init__(self, encoding_name: str = "o200k_base") -> None:
        self.encoding_name = encoding_name
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))
```

- [ ] **Step 5: 实现配置**

`src/docchunk/config.py`:

```python
import shutil
from pathlib import Path

from pydantic import BaseModel, Field


_MINERU_VENV_FALLBACK = Path.home() / ".venvs" / "mineru" / "bin" / "mineru"


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
```

本机适配说明（2026-08-29）：

- `corpus_root` 默认指向 `/Volumes/ORICO/LongDocCorpus`（外接 APFS 数据盘，与 MinerU 模型同盘）；所有测试使用 `tmp_path`，不受默认值影响。
- `resolve_mineru_command()`：显式配置优先 → PATH 查找 → 回退 `~/.venvs/mineru/bin/mineru`；`MinerUAdapter` 在构造时调用它，doctor 也用它展示解析结果。
- `mineru_backend` / `mineru_effort` 把本机约定（`hybrid-engine` / `medium`）显式化，Task 6 的 argv 使用它们。

在 `tests/test_tokenizer.py` 补充解析逻辑测试：

```python
from docchunk.config import AppConfig, resolve_mineru_command


def test_mineru_command_resolution(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "mineru"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    monkeypatch.setattr("docchunk.config.shutil.which", lambda name: str(fake))
    assert resolve_mineru_command() == str(fake)

    monkeypatch.setattr("docchunk.config.shutil.which", lambda name: None)
    monkeypatch.setattr("docchunk.config._MINERU_VENV_FALLBACK", fake)
    assert resolve_mineru_command() == str(fake)

    assert resolve_mineru_command("/custom/mineru") == "/custom/mineru"
    assert AppConfig().mineru_backend == "hybrid-engine"
```

- [ ] **Step 6: 跑测试**

```bash
uv run pytest tests/test_tokenizer.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 7: 提交**

```bash
git add src/docchunk/config.py src/docchunk/fingerprints.py src/docchunk/tokenizer.py tests/test_tokenizer.py
git commit -m "feat: add config fingerprints and tokenizer"
```

---

## Task 4: 定义 Adapter 接口并实现 Markdown/TXT 标准化

**目标：** 让 Markdown/TXT 先成为第一组可真实处理的输入。

**Files:**
- Create: `src/docchunk/adapters/base.py`
- Create: `src/docchunk/adapters/markdown.py`
- Create: `src/docchunk/adapters/text.py`
- Create: `src/docchunk/adapters/__init__.py`
- Create: `tests/test_markdown_adapter.py`
- Create: `tests/test_text_adapter.py`

**Interfaces:**
- Produces `NormalizedDocument`
- Produces `DocumentAdapter.prepare(path: Path) -> NormalizedDocument`
- Produces `MarkdownAdapter`
- Produces `TextAdapter`

- [ ] **Step 1: 写 Markdown 失败测试**

```python
from pathlib import Path

from docchunk.adapters.markdown import MarkdownAdapter


def test_markdown_adapter_normalizes_line_endings(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_bytes("# 第一章\r\n\r\n第一段。\r\n".encode("utf-8"))

    doc = MarkdownAdapter().prepare(source)

    assert doc.text == "# 第一章\n\n第一段。\n"
    assert doc.source_path == source
    assert doc.media_type == "text/markdown"
```

- [ ] **Step 2: 写 TXT 失败测试**

```python
from pathlib import Path

from docchunk.adapters.text import TextAdapter


def test_text_adapter_preserves_paragraphs(tmp_path: Path) -> None:
    source = tmp_path / "course.txt"
    source.write_text("第一段。\n\n第二段。", encoding="utf-8")

    doc = TextAdapter().prepare(source)

    assert doc.text == "第一段。\n\n第二段。"
    assert doc.media_type == "text/plain"
```

- [ ] **Step 3: 确认失败**

```bash
uv run pytest tests/test_markdown_adapter.py tests/test_text_adapter.py -v
```

- [ ] **Step 4: 实现基础模型和换行标准化**

`src/docchunk/adapters/base.py`:

```python
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


class DocumentAdapter(ABC):
    @abstractmethod
    def prepare(self, path: Path) -> NormalizedDocument:
        raise NotImplementedError


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
```

- [ ] **Step 5: 实现 Markdown Adapter**

```python
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings


class MarkdownAdapter(DocumentAdapter):
    def prepare(self, path: Path) -> NormalizedDocument:
        text = normalize_line_endings(path.read_text(encoding="utf-8"))
        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=text,
        )
```

- [ ] **Step 6: 实现 TXT Adapter**

```python
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings


class TextAdapter(DocumentAdapter):
    def prepare(self, path: Path) -> NormalizedDocument:
        text = normalize_line_endings(path.read_text(encoding="utf-8"))
        return NormalizedDocument(
            source_path=path,
            media_type="text/plain",
            text=text,
        )
```

- [ ] **Step 7: 跑测试**

```bash
uv run pytest tests/test_markdown_adapter.py tests/test_text_adapter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 8: 提交**

```bash
git add src/docchunk/adapters tests/test_markdown_adapter.py tests/test_text_adapter.py
git commit -m "feat: add markdown and text adapters"
```

---

## Task 5: 实现 Pandoc DOCX Adapter

**目标：** DOCX 默认经 Pandoc 生成 Markdown；Pandoc 不存在或失败时明确报错，不静默 fallback。

**Files:**
- Create: `src/docchunk/errors.py`
- Create: `src/docchunk/adapters/pandoc.py`
- Create: `tests/test_pandoc_adapter.py`

**Interfaces:**
- Produces `ExternalToolError`
- Produces `PandocAdapter.prepare(path: Path) -> NormalizedDocument`

- [ ] **Step 1: 写失败测试，不依赖真实 Pandoc**

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from docchunk.adapters.pandoc import PandocAdapter
from docchunk.errors import ExternalToolError


def test_pandoc_adapter_reads_stdout_markdown(tmp_path: Path) -> None:
    source = tmp_path / "book.docx"
    source.write_bytes(b"fake-docx")

    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "# 标题\n\n正文。\n"
        run.return_value.stderr = ""

        doc = PandocAdapter().prepare(source)

    assert doc.text == "# 标题\n\n正文。\n"
    assert doc.metadata["adapter"] == "pandoc"


def test_pandoc_failure_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "book.docx"
    source.write_bytes(b"fake-docx")

    with patch("subprocess.run") as run:
        run.return_value.returncode = 2
        run.return_value.stdout = ""
        run.return_value.stderr = "bad docx"

        with pytest.raises(ExternalToolError, match="Pandoc failed"):
            PandocAdapter().prepare(source)
```

- [ ] **Step 2: 确认失败**

```bash
uv run pytest tests/test_pandoc_adapter.py -v
```

- [ ] **Step 3: 实现错误类型**

`src/docchunk/errors.py`:

```python
class DocchunkError(Exception):
    """Base error for docchunk."""


class ExternalToolError(DocchunkError):
    """Raised when MinerU or Pandoc fails."""


class VerificationError(DocchunkError):
    """Raised when a generated corpus fails integrity checks."""


class UnsupportedInputError(DocchunkError):
    """Raised when no adapter supports an input."""
```

- [ ] **Step 4: 实现 Pandoc Adapter**

```python
import subprocess
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings
from docchunk.errors import ExternalToolError


class PandocAdapter(DocumentAdapter):
    def prepare(self, path: Path) -> NormalizedDocument:
        try:
            result = subprocess.run(
                ["pandoc", str(path), "-f", "docx", "-t", "gfm"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise ExternalToolError("Pandoc executable was not found") from exc

        if result.returncode != 0:
            raise ExternalToolError(f"Pandoc failed: {result.stderr.strip()}")

        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=normalize_line_endings(result.stdout),
            metadata={"adapter": "pandoc"},
        )
```

- [ ] **Step 5: 跑测试**

```bash
uv run pytest tests/test_pandoc_adapter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 6: 手工环境验证**

```bash
pandoc --version
```

本机（2026-08-29 核实）：Pandoc 3.11 已安装在 `/usr/local/bin/pandoc`（官方 pkg，已在 PATH），此步直接通过；按 `~/.codex/AGENTS.md` 第 16 节约定，**不要**再用 Homebrew 重装。

如果在新机器上提示：

```text
command not found: pandoc
```

Mac 通用安装方式：

```bash
brew install pandoc
```

安装后再次：

```bash
pandoc --version
```

- [ ] **Step 7: 提交**

```bash
git add src/docchunk/errors.py src/docchunk/adapters/pandoc.py tests/test_pandoc_adapter.py
git commit -m "feat: add pandoc docx adapter"
```

---

## Task 6: 实现 MinerU PDF Adapter 与可落到 Markdown 字符位置的页码 provenance

**目标：** PDF 经 MinerU 处理后，不只读取 `.md`，还读取 `content_list.json`。MinerU 的 `page_idx` 是页级来源信息，但它本身不是 Markdown 字符 offset，因此本 Task 必须把内容块重新对齐到 `normalized.md` 的字符位置，再供 Atomic Chunk 映射页码。

**Files:**
- Create: `src/docchunk/adapters/mineru.py`
- Create: `src/docchunk/provenance/mineru.py`
- Create: `src/docchunk/provenance/__init__.py`
- Create: `tests/fixtures/mineru-normalized.md`
- Create: `tests/fixtures/mineru-content-list.json`
- Create: `tests/test_mineru_adapter.py`

**Interfaces:**
- Produces `MinerUAdapter(command: str = "mineru", backend: str = "hybrid-engine", effort: str = "medium")`（command 在构造时经 `resolve_mineru_command()` 解析）
- Produces `parse_content_list(content: list[dict[str, object]]) -> list[NormalizedBlock]`
- Produces `align_blocks_to_markdown(markdown: str, blocks: list[NormalizedBlock]) -> list[NormalizedBlock]`
- Produces `source_pages_for_span(blocks, char_start, char_end) -> tuple[int | None, int | None]`
- `NormalizedBlock.page_idx` 保留 MinerU 的 **0-based** `page_idx`
- 对外 `SourceLocation.page_start/page_end` 最终使用 **1-based** 人类页码

**测试 fixture：**

`tests/fixtures/mineru-normalized.md`:

```markdown
# 第一章

这是第一页正文。

## 第二节

这是第二页正文。
```

`tests/fixtures/mineru-content-list.json`:

```json
[
  {
    "type": "text",
    "text": "第一章",
    "text_level": 1,
    "page_idx": 0,
    "bbox": [10, 10, 100, 30]
  },
  {
    "type": "text",
    "text": "这是第一页正文。",
    "page_idx": 0,
    "bbox": [10, 40, 200, 80]
  },
  {
    "type": "text",
    "text": "第二节",
    "text_level": 2,
    "page_idx": 1,
    "bbox": [10, 10, 100, 30]
  },
  {
    "type": "text",
    "text": "这是第二页正文。",
    "page_idx": 1,
    "bbox": [10, 40, 200, 80]
  }
]
```

- [ ] **Step 1: 写解析与对齐失败测试**

`tests/test_mineru_adapter.py`:

```python
import json
from pathlib import Path

from docchunk.provenance.mineru import (
    align_blocks_to_markdown,
    parse_content_list,
    source_pages_for_span,
)


def _fixture_blocks():
    path = Path("tests/fixtures/mineru-content-list.json")
    content = json.loads(path.read_text(encoding="utf-8"))
    return parse_content_list(content)


def test_content_list_keeps_mineru_zero_based_page_index() -> None:
    blocks = _fixture_blocks()

    assert blocks[0].page_idx == 0
    assert blocks[2].page_idx == 1
    assert blocks[0].heading_level == 1
    assert blocks[2].heading_level == 2


def test_blocks_are_aligned_to_real_markdown_offsets() -> None:
    markdown = Path("tests/fixtures/mineru-normalized.md").read_text(encoding="utf-8")
    blocks = align_blocks_to_markdown(markdown, _fixture_blocks())

    first_body = blocks[1]
    assert markdown[first_body.char_start:first_body.char_end] == "这是第一页正文。"


def test_atomic_span_maps_to_human_page_numbers() -> None:
    markdown = Path("tests/fixtures/mineru-normalized.md").read_text(encoding="utf-8")
    blocks = align_blocks_to_markdown(markdown, _fixture_blocks())

    second_start = markdown.index("第二节")
    page_start, page_end = source_pages_for_span(
        blocks,
        char_start=second_start,
        char_end=len(markdown),
    )

    assert (page_start, page_end) == (2, 2)
```

- [ ] **Step 2: 运行并确认失败**

```bash
uv run pytest tests/test_mineru_adapter.py -v
```

Expected: `docchunk.provenance.mineru` 不存在或函数未定义。

- [ ] **Step 3: 实现 `parse_content_list`**

`src/docchunk/provenance/mineru.py`:

```python
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
        # Step 4 会重新对齐。
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
```

- [ ] **Step 4: 实现 Markdown 对齐**

同文件增加：

```python
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
            # 不伪造 offset，保留 block 但将 offset 设为 -1 语义不可取，
            # 因模型字段要求 >=0，所以直接跳过未对齐 block，
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
```

**为什么不能直接把 `content_list.json` 的 block 顺序累计成字符 offset：**

因为 MinerU Markdown 会加入 `#`、`##`、空行、Markdown 表格符号等内容。只有在最终 normalized Markdown 中重新定位，Atomic 的 `char_start/char_end` 才能与页码 provenance 使用同一坐标系。

- [ ] **Step 5: 实现 Atomic span → PDF 页码**

```python
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
```

- [ ] **Step 6: 写 MinerU Adapter mock 测试**

在 `tests/test_mineru_adapter.py` 增加：

```python
from unittest.mock import patch

from docchunk.adapters.mineru import MinerUAdapter


def test_mineru_adapter_uses_generated_markdown_and_content_list(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-fake")

    output = tmp_path / "mineru-output"
    output.mkdir()
    (output / "book.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    (output / "book_content_list.json").write_text(
        '[{"type":"text","text":"标题","text_level":1,"page_idx":0},'
        '{"type":"text","text":"正文。","page_idx":0}]',
        encoding="utf-8",
    )

    with patch.object(MinerUAdapter, "_run_mineru", return_value=output):
        doc = MinerUAdapter().prepare(pdf)

    assert doc.text.startswith("# 标题")
    assert doc.blocks[0].page_idx == 0
    assert doc.blocks[0].char_start == doc.text.index("标题")
    assert doc.metadata["adapter"] == "mineru"
    assert doc.metadata["unaligned_blocks"] == 0
```

- [ ] **Step 7: 实现 MinerU Adapter**

`src/docchunk/adapters/mineru.py`:

```python
import json
import subprocess
import tempfile
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings
from docchunk.config import resolve_mineru_command
from docchunk.errors import ExternalToolError
from docchunk.provenance.mineru import align_blocks_to_markdown, parse_content_list


class MinerUAdapter(DocumentAdapter):
    def __init__(
        self,
        command: str = "mineru",
        backend: str = "hybrid-engine",
        effort: str = "medium",
    ) -> None:
        self.command = resolve_mineru_command(command)
        self.backend = backend
        self.effort = effort

    def _run_mineru(self, path: Path) -> Path:
        output_root = Path(tempfile.mkdtemp(prefix="docchunk-mineru-"))

        try:
            result = subprocess.run(
                [
                    self.command,
                    "-p", str(path),
                    "-o", str(output_root),
                    "-b", self.backend,
                    "--effort", self.effort,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise ExternalToolError("MinerU executable was not found") from exc

        if result.returncode != 0:
            raise ExternalToolError(f"MinerU failed: {result.stderr.strip()}")

        return output_root

    def prepare(self, path: Path) -> NormalizedDocument:
        output_root = self._run_mineru(path)
        markdown_files = sorted(output_root.rglob(f"{path.stem}.md"))
        # 兼容 v1/v2 命名：*_content_list.json / *_content_list_v2.json
        content_files = sorted(output_root.rglob(f"{path.stem}_content_list*.json"))

        if not markdown_files:
            raise ExternalToolError("MinerU completed but no Markdown output was found")

        markdown_path = markdown_files[0]
        text = normalize_line_endings(markdown_path.read_text(encoding="utf-8"))

        parsed_blocks = []
        aligned_blocks = []
        if content_files:
            raw = json.loads(content_files[0].read_text(encoding="utf-8"))
            if isinstance(raw, list):
                parsed_blocks = parse_content_list(raw)
                aligned_blocks = align_blocks_to_markdown(text, parsed_blocks)

        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=text,
            blocks=aligned_blocks,
            metadata={
                "adapter": "mineru",
                "mineru_output_root": str(output_root),
                "parsed_blocks": len(parsed_blocks),
                "aligned_blocks": len(aligned_blocks),
                "unaligned_blocks": len(parsed_blocks) - len(aligned_blocks),
            },
        )
```

- [ ] **Step 8: 跑测试**

```bash
uv run pytest tests/test_mineru_adapter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 9: MinerU 命令核对结论（2026-08-29 已完成）**

本机 MinerU 3.4.5 的 `--help` 已核对，结论如下，`_run_mineru()` 按此实现，无需再试探：

```text
# 实际可执行文件（不在 PATH，代码经 resolve_mineru_command() 解析）：
~/.venvs/mineru/bin/mineru

# CLI 契约：-p/-o 均必填；工具自身默认 backend 就是 hybrid-engine、effort 默认 medium；
# docchunk 仍显式传 -b 与 --effort，保证不依赖工具默认值：
mineru -p INPUT -o OUTPUT_DIR -b hybrid-engine --effort medium
```

注意：3.4.5 没有 `--source` 参数（模型源由 `~/mineru.json` 决定，该文件禁止修改）。如未来 MinerU 升级导致参数变化，只允许修改 `_run_mineru()` 里的 argv；`prepare()`、`NormalizedDocument`、`content_list` 解析和 provenance 契约都不要跟着变。

- [ ] **Step 10: 用 2–5 页中文 PDF 做真实 smoke test**

手工运行 MinerU（不在 PATH，用完整路径）后确认输出至少存在：

```bash
~/.venvs/mineru/bin/mineru -p <2-5页中文PDF> -o /tmp/mineru-smoke \
  -b hybrid-engine --effort medium
```

```text
book.md
book_content_list.json   # 或 book_content_list_v2.json，发现逻辑两者都兼容
```

MinerU 会把输出嵌套在 `<output>/<文件名>/<backend>/` 等子目录中，Adapter 用 `rglob()` 发现文件，已兼容嵌套。若真实输出命名仍有差异，则只调整“发现生成文件”的 glob 规则，测试中的固定数据契约不变。

- [ ] **Step 11: 提交**

```bash
git add src/docchunk/adapters/mineru.py \
        src/docchunk/provenance \
        tests/fixtures/mineru-normalized.md \
        tests/fixtures/mineru-content-list.json \
        tests/test_mineru_adapter.py
git commit -m "feat: add mineru pdf adapter with aligned provenance"
```

## Task 7: 输入识别、Adapter 路由和目录 Document Set

**目标：** `docchunk` 可以接受单个文件或一个目录；目录中的文件采用自然排序，保留独立 document_id。

**Files:**
- Create: `src/docchunk/adapters/directory.py`
- Create: `src/docchunk/inspect_input.py`
- Create: `tests/test_directory_adapter.py`

**Interfaces:**
- Produces `discover_inputs(path: Path) -> list[Path]`
- Produces `choose_adapter(path: Path) -> DocumentAdapter`
- Supports `.pdf/.docx/.md/.markdown/.txt`

- [ ] **Step 1: 写目录排序失败测试**

```python
from pathlib import Path

from docchunk.adapters.directory import discover_inputs


def test_directory_uses_natural_numeric_order(tmp_path: Path) -> None:
    for name in ["10-第十课.md", "2-第二课.md", "1-第一课.md", "ignore.jpg"]:
        (tmp_path / name).write_text("x", encoding="utf-8")

    files = discover_inputs(tmp_path)

    assert [path.name for path in files] == [
        "1-第一课.md",
        "2-第二课.md",
        "10-第十课.md",
    ]
```

- [ ] **Step 2: 确认失败**

```bash
uv run pytest tests/test_directory_adapter.py -v
```

- [ ] **Step 3: 实现自然排序**

`src/docchunk/adapters/directory.py`:

```python
import re
from pathlib import Path

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt"}


def _natural_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.casefold())
    return [int(part) if part.isdigit() else part for part in parts]


def discover_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    if not path.is_dir():
        raise FileNotFoundError(path)

    files = [
        item
        for item in path.iterdir()
        if item.is_file() and item.suffix.casefold() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=_natural_key)
```

- [ ] **Step 4: 实现 Adapter 路由**

`src/docchunk/inspect_input.py`:

```python
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pandoc import PandocAdapter
from docchunk.adapters.text import TextAdapter
from docchunk.errors import UnsupportedInputError


def choose_adapter(path: Path) -> DocumentAdapter:
    suffix = path.suffix.casefold()

    if suffix in {".md", ".markdown"}:
        return MarkdownAdapter()
    if suffix == ".txt":
        return TextAdapter()
    if suffix == ".docx":
        return PandocAdapter()
    if suffix == ".pdf":
        return MinerUAdapter()

    raise UnsupportedInputError(f"Unsupported input type: {suffix or '<none>'}")
```

- [ ] **Step 5: 补 Adapter 路由测试**

```python
from pathlib import Path

import pytest

from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.errors import UnsupportedInputError
from docchunk.inspect_input import choose_adapter


def test_choose_markdown_adapter() -> None:
    assert isinstance(choose_adapter(Path("a.md")), MarkdownAdapter)


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedInputError):
        choose_adapter(Path("a.jpg"))
```

- [ ] **Step 6: 跑测试**

```bash
uv run pytest tests/test_directory_adapter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 7: 提交**

```bash
git add src/docchunk/adapters/directory.py src/docchunk/inspect_input.py tests/test_directory_adapter.py
git commit -m "feat: add input discovery and adapter routing"
```

---

## Task 8: 用 `semantic-text-splitter` 实现真正的 Token-aware Atomic Splitter

**目标：** V1 不自己重新发明 Unicode/Markdown 语义边界算法。使用 `semantic-text-splitter` 的 `TextSplitter/MarkdownSplitter` 作为核心；使用项目自己的 `TokenCounter` 作为 callback；必须设置 `trim=False` 和 `overlap=0`，保证 `join(chunks) == normalized source`。

**为什么这样做：**
- `semantic-text-splitter` 原生支持 Unicode grapheme/word/sentence boundary；
- `MarkdownSplitter` 使用 CommonMark/GFM 结构层级；
- 当前 Python binding 支持 `from_callback(callback, capacity, overlap=0, trim=true)`；
- 当前 Python binding 支持 `chunk_indices(text)`，直接返回 `(char_offset, chunk)`；
- `trim=False` 时官方契约明确保证所有 chunk 重新拼接可返回原字符串；
- 这正好满足“自然语言边界 + token 预算 + lossless + source offset”。

**Files:**
- Create: `src/docchunk/splitting/boundaries.py`
- Create: `src/docchunk/splitting/atomic.py`
- Create: `tests/test_atomic_splitter.py`

**Interfaces:**
- Produces `HeadingMark`
- Produces `AtomicChunk`
- Produces `extract_heading_marks(text: str) -> list[HeadingMark]`
- Produces `heading_path_at(marks, char_offset) -> list[str]`
- Produces `split_atomic(text, counter, policy, markdown) -> list[AtomicChunk]`

- [ ] **Step 1: 用一条命令确认已安装库的 API**

执行：

```bash
uv run python - <<'PY'
from semantic_text_splitter import MarkdownSplitter
print(MarkdownSplitter.from_callback)
print(MarkdownSplitter.chunk_indices)
PY
```

Expected: 两个属性均能打印，不出现 `AttributeError`。

如果失败，不要改架构；先执行：

```bash
uv sync
uv pip show semantic-text-splitter
```

确认 Task 1 的依赖实际安装。

- [ ] **Step 2: 写“短文不切且字节内容不变”失败测试**

`tests/test_atomic_splitter.py`:

```python
from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.atomic import split_atomic
from docchunk.tokenizer import TokenCounter


def test_short_text_remains_one_atomic_chunk() -> None:
    text = "# 第一章\n\n第一段。\n\n第二段。"
    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=6000,
            soft_min_tokens=4000,
            soft_max_tokens=8000,
        ),
        markdown=True,
    )

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
```

- [ ] **Step 3: 写“长中文自然拆分但可无损重组”测试**

```python
def test_long_chinese_text_is_lossless() -> None:
    text = (
        "# 第一节\n\n"
        + "这是第一段。这里继续解释第一段的概念。" * 40
        + "\n\n"
        + "这是第二段。这里继续给出第二段的案例。" * 40
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=80,
            soft_min_tokens=40,
            soft_max_tokens=110,
        ),
        markdown=True,
    )

    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == text
```

- [ ] **Step 4: 写 offset 连续性测试**

```python
def test_atomic_offsets_are_contiguous() -> None:
    text = ("第一段。" * 80) + "\n\n" + ("第二段。" * 80)

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=60,
            soft_min_tokens=30,
            soft_max_tokens=90,
        ),
        markdown=False,
    )

    assert chunks[0].char_start == 0
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.char_end == current.char_start
    assert chunks[-1].char_end == len(text)
```

- [ ] **Step 5: 写 heading path 测试**

```python
def test_heading_path_follows_markdown_structure() -> None:
    text = (
        "# 第一章\n\n"
        "开头。\n\n"
        "## 第二节\n\n"
        + ("这一节内容。" * 100)
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=40,
            soft_min_tokens=20,
            soft_max_tokens=60,
        ),
        markdown=True,
    )

    second_section = [chunk for chunk in chunks if "这一节内容" in chunk.text]
    assert second_section
    assert second_section[0].heading_path == ["第一章", "第二节"]
```

- [ ] **Step 6: 确认测试先失败**

```bash
uv run pytest tests/test_atomic_splitter.py -v
```

- [ ] **Step 7: 实现 heading 位置模型**

`src/docchunk/splitting/boundaries.py`:

```python
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
```

- [ ] **Step 8: 实现 AtomicChunk 与 forced-boundary 诊断**

`src/docchunk/splitting/atomic.py`:

```python
from pydantic import BaseModel
from semantic_text_splitter import MarkdownSplitter, TextSplitter

from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.boundaries import extract_heading_marks, heading_path_at
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

    chunks: list[AtomicChunk] = []
    for sequence, (char_start, chunk_text) in enumerate(raw_chunks, start=1):
        char_end = char_start + len(chunk_text)
        chunks.append(
            AtomicChunk(
                sequence=sequence,
                text=chunk_text,
                token_count=counter.count(chunk_text),
                char_start=char_start,
                char_end=char_end,
                heading_path=heading_path_at(marks, char_start),
                forced_split=_looks_like_forced_boundary(text, char_end),
            )
        )

    if "".join(chunk.text for chunk in chunks) != text:
        raise ValueError("Atomic splitter changed normalized source text")

    return chunks
```

**说明：**
- `forced_split` 是诊断 flag，不声称能获得 splitter 内部的精确语义层级；
- 真正的强保证是 `trim=False + overlap=0 + chunk_indices`；
- V1 不因为 forced flag 再二次改写文本。

- [ ] **Step 9: 增加 Atomic token 上界测试**

```python
def test_atomic_chunks_respect_soft_max_except_diagnostic_cases() -> None:
    text = ("这是一个完整句子。" * 300)

    policy = AtomicPolicy(
        target_tokens=50,
        soft_min_tokens=30,
        soft_max_tokens=70,
    )
    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=policy,
        markdown=False,
    )

    assert all(chunk.token_count <= policy.soft_max_tokens for chunk in chunks)
```

- [ ] **Step 10: 跑全套**

```bash
uv run pytest tests/test_atomic_splitter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 11: 提交**

```bash
git add src/docchunk/splitting tests/test_atomic_splitter.py
git commit -m "feat: add token-aware semantic atomic splitter"
```

## Task 9: Markdown 特殊结构标注：表格表头上下文、代码块与列表保护

**目标：** `MarkdownSplitter` 已经负责 CommonMark/GFM 语义层级，因此 V1 不再自己写第二套 Markdown parser。这里只补一个它目前不保证的体验：当超长 Markdown 表格跨多个 Atomic 时，后续片段需要知道原表头。表头只能作为 **synthetic context metadata**，绝不能复制进 Atomic 原文，否则会破坏 lossless。

**设计澄清：**
- Atomic `text` 永远只保存原文；
- `join(atomic.text) == normalized source` 永远成立；
- 若一个 Atomic 位于同一表格的后半段，可记录 `table_header_context`；
- Reading Batch 渲染时可以把该表头显示成“上下文提示”，但明确标记“非新原文”；
- 这样同时满足“超长表格可读”和“Chunking lossless”。

**Files:**
- Create: `src/docchunk/splitting/structured_blocks.py`
- Modify: `src/docchunk/splitting/atomic.py`
- Create: `tests/test_structured_blocks.py`
- Create: `tests/fixtures/tables.md`

**Interfaces:**
- Produces `MarkdownTable`
- Produces `find_markdown_tables(text: str) -> list[MarkdownTable]`
- Produces `table_context_for_span(tables, char_start, char_end) -> tuple[bool, str | None]`

- [ ] **Step 1: 写表格 fixture**

`tests/fixtures/tables.md`:

```markdown
# 数据

| 姓名 | 金额 |
| --- | ---: |
| 甲 | 100 |
| 乙 | 200 |
| 丙 | 300 |

后续正文。
```

- [ ] **Step 2: 写表格识别失败测试**

`tests/test_structured_blocks.py`:

```python
from pathlib import Path

from docchunk.splitting.structured_blocks import find_markdown_tables


def test_table_span_and_header_are_detected() -> None:
    text = Path("tests/fixtures/tables.md").read_text(encoding="utf-8")
    tables = find_markdown_tables(text)

    assert len(tables) == 1
    assert tables[0].header == "| 姓名 | 金额 |\n| --- | ---: |\n"
    assert text[tables[0].char_start:tables[0].char_end].startswith("| 姓名 |")
```

- [ ] **Step 3: 写“Atomic 原文不能重复表头”测试**

```python
from docchunk.models.manifest import AtomicPolicy
from docchunk.splitting.atomic import split_atomic
from docchunk.tokenizer import TokenCounter


def test_table_context_never_changes_atomic_source_text() -> None:
    text = (
        "# 表\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        + "".join(f"| row{i} | value{i} |\n" for i in range(200))
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=80,
            soft_min_tokens=40,
            soft_max_tokens=110,
        ),
        markdown=True,
    )

    assert "".join(chunk.text for chunk in chunks) == text
    assert any(chunk.table_header_context for chunk in chunks[1:])
```

- [ ] **Step 4: 确认失败**

```bash
uv run pytest tests/test_structured_blocks.py -v
```

- [ ] **Step 5: 实现表格 span 识别**

`src/docchunk/splitting/structured_blocks.py`:

```python
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
```

- [ ] **Step 6: 在 `split_atomic()` 中只增加 metadata，不修改 chunk text**

在 `atomic.py`：

```python
from docchunk.splitting.structured_blocks import (
    find_markdown_tables,
    table_context_for_span,
)
```

创建 chunk 前：

```python
tables = find_markdown_tables(text) if markdown else []
```

循环中：

```python
split_table, table_header_context = table_context_for_span(
    tables,
    char_start,
    char_end,
)
```

并写入：

```python
split_table=split_table,
table_header_context=table_header_context,
```

禁止执行：

```python
chunk_text = table_header_context + chunk_text
```

因为这会破坏无损性。

- [ ] **Step 7: 确认 fenced code block 在合理预算下不会被无故拆坏**

增加：

```python
def test_small_fenced_code_block_remains_inside_one_chunk() -> None:
    text = (
        "# 示例\n\n"
        "前文。\n\n"
        "```python\n"
        "print('x')\n"
        "print('y')\n"
        "```\n\n"
        "后文。\n"
    )

    chunks = split_atomic(
        text=text,
        counter=TokenCounter(),
        policy=AtomicPolicy(
            target_tokens=200,
            soft_min_tokens=100,
            soft_max_tokens=260,
        ),
        markdown=True,
    )

    matching = [chunk for chunk in chunks if "print('x')" in chunk.text]
    assert len(matching) == 1
    assert "print('y')" in matching[0].text
```

- [ ] **Step 8: 跑测试**

```bash
uv run pytest tests/test_structured_blocks.py tests/test_atomic_splitter.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 9: 提交**

```bash
git add src/docchunk/splitting tests/test_structured_blocks.py tests/fixtures/tables.md
git commit -m "feat: annotate markdown table context without source duplication"
```

## Task 10: Atomic 文件、`index.jsonl`、`manifest.json` 的持久化

**目标：** 把内存数据写成稳定、可恢复、对人可读的 Corpus。`index.jsonl` 是 Atomic metadata 的权威索引；Atomic `.md` 文件只保存少量高频 frontmatter + **原样正文**。

**Files:**
- Create: `src/docchunk/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Produces `CorpusPaths`
- Produces `create_corpus_layout(root: Path, corpus_id: str) -> CorpusPaths`
- Produces `write_atomic_chunk(paths: CorpusPaths, record: AtomicIndexRecord, text: str) -> None`
- Produces `read_atomic_body(path: Path) -> str`
- Produces `append_index_record(paths: CorpusPaths, record: AtomicIndexRecord) -> None`
- Produces `write_combined_view(paths: CorpusPaths, records: list[AtomicIndexRecord]) -> None`
- Produces `write_manifest(paths: CorpusPaths, manifest: Manifest) -> None`

- [ ] **Step 1: 写失败测试**

`tests/test_storage.py`:

```python
import json
from pathlib import Path

from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.storage import (
    append_index_record,
    create_corpus_layout,
    write_atomic_chunk,
)


def test_storage_writes_atomic_and_jsonl(tmp_path: Path) -> None:
    paths = create_corpus_layout(tmp_path, "demo")
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=5,
        char_start=0,
        char_end=4,
        heading_path=["第一章", '带"引号"的小节'],
        source=SourceLocation(file="a.md"),
        flags=AtomicFlags(),
    )

    write_atomic_chunk(paths, record, "正文")
    append_index_record(paths, record)

    atomic = paths.atomic_dir / "A000001.md"
    assert atomic.exists()
    content = atomic.read_text(encoding="utf-8")
    assert content.endswith("\n\n正文")
    assert "A000001" in content

    lines = paths.index_jsonl.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["atomic_id"] == "A000001"
```

- [ ] **Step 2: 运行并确认失败**

```bash
uv run pytest tests/test_storage.py -v
```

- [ ] **Step 3: 实现 `CorpusPaths`**

`src/docchunk/storage.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusPaths:
    root: Path
    source_dir: Path
    atomic_dir: Path
    batches_dir: Path
    logs_dir: Path
    manifest_json: Path
    index_jsonl: Path
    combined_md: Path
    state_json: Path


def create_corpus_layout(root: Path, corpus_id: str) -> CorpusPaths:
    corpus_root = root / corpus_id
    paths = CorpusPaths(
        root=corpus_root,
        source_dir=corpus_root / "source",
        atomic_dir=corpus_root / "atomic",
        batches_dir=corpus_root / "batches",
        logs_dir=corpus_root / "logs",
        manifest_json=corpus_root / "manifest.json",
        index_jsonl=corpus_root / "index.jsonl",
        combined_md=corpus_root / "combined.md",
        state_json=corpus_root / "state.json",
    )

    for directory in (
        paths.root,
        paths.source_dir,
        paths.atomic_dir,
        paths.batches_dir,
        paths.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return paths
```

- [ ] **Step 4: 实现安全 frontmatter 写入**

不要自己拼接未经转义的 YAML 字符串。JSON 字符串是合法 YAML scalar，因此使用 `json.dumps()` 做转义。

同文件增加：

```python
import json

from docchunk.models.index import AtomicIndexRecord
from docchunk.models.manifest import Manifest, utc_now_iso


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_atomic_chunk(
    paths: CorpusPaths,
    record: AtomicIndexRecord,
    text: str,
) -> None:
    target = paths.root / record.path
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f"atomic_id: {_yaml_string(record.atomic_id)}",
        f"document_id: {_yaml_string(record.document_id)}",
        f"sequence: {record.sequence}",
        f"tokens: {record.token_count}",
        f"source_file: {_yaml_string(record.source.file)}",
        (
            "page_start: null"
            if record.source.page_start is None
            else f"page_start: {record.source.page_start}"
        ),
        (
            "page_end: null"
            if record.source.page_end is None
            else f"page_end: {record.source.page_end}"
        ),
    ]

    if record.heading_path:
        lines.append("heading_path:")
        lines.extend(f"  - {_yaml_string(item)}" for item in record.heading_path)
    else:
        lines.append("heading_path: []")

    lines.extend(["---", "", text])
    target.write_text("\n".join(lines), encoding="utf-8")
```

**重要：** `text` 进入 `write_atomic_chunk()` 后禁止 `.strip()`、`.rstrip()` 或自动追加正文换行；否则 verify 无法无损重建 normalized source。

- [ ] **Step 5: 实现 JSONL 与 Manifest**

同文件增加：

```python
def append_index_record(paths: CorpusPaths, record: AtomicIndexRecord) -> None:
    with paths.index_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def write_manifest(paths: CorpusPaths, manifest: Manifest) -> None:
    manifest.updated_at = utc_now_iso()
    paths.manifest_json.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )


def read_atomic_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Atomic file has no frontmatter: {path}")

    closing = content.find("\n---\n", 4)
    if closing < 0:
        raise ValueError(f"Atomic frontmatter is not closed: {path}")

    body_start = closing + len("\n---\n")
    if content[body_start:body_start + 1] == "\n":
        body_start += 1
    return content[body_start:]


def write_combined_view(
    paths: CorpusPaths,
    records: list[AtomicIndexRecord],
) -> None:
    lines = [
        "# docchunk Combined Atomic View",
        "",
        "> 这是派生阅读视图。权威原文是 source/documents/*/normalized.md；"
        "权威切片索引是 index.jsonl。",
        "",
    ]

    for record in records:
        atomic_path = paths.root / record.path
        body = read_atomic_body(atomic_path)
        lines.extend(
            [
                f"## {record.atomic_id}",
                "",
                f"- document_id: `{record.document_id}`",
                f"- source: `{record.source.file}`",
                f"- char_range: `{record.char_start}:{record.char_end}`",
                (
                    f"- pages: `{record.source.page_start}-{record.source.page_end}`"
                    if record.source.page_start is not None
                    else "- pages: `n/a`"
                ),
                "",
                body,
                "",
            ]
        )

    paths.combined_md.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 6: 增加“正文不能被 strip”测试**

```python
def test_atomic_storage_preserves_body_whitespace(tmp_path: Path) -> None:
    paths = create_corpus_layout(tmp_path, "demo")
    record = AtomicIndexRecord(
        atomic_id="A000001",
        document_id="D0001",
        sequence=1,
        path="atomic/A000001.md",
        token_count=1,
        char_start=0,
        char_end=8,
        source=SourceLocation(file="a.md"),
    )
    body = "\n正文\n\n"

    write_atomic_chunk(paths, record, body)

    content = (paths.atomic_dir / "A000001.md").read_text(encoding="utf-8")
    assert content.endswith("\n\n" + body)
```

- [ ] **Step 7: 跑测试**

```bash
uv run pytest tests/test_storage.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 8: 提交**

```bash
git add src/docchunk/storage.py tests/test_storage.py
git commit -m "feat: persist corpus atomic files and indexes"
```

## Task 11: Reading Batch Builder：完整 Atomic overlap + context-only 表格表头

**目标：** Atomic 永远不变，通过完整 Atomic 组合出约 24K Token 的 Reading Batch。相邻 Batch 默认重复 1 个完整 Atomic 作为 `Context Bridge`。若 Atomic metadata 里存在 `table_header`，Batch 可以在阅读视图中补充“synthetic context”，但必须明确标记其不是新的原文。

**Files:**
- Create: `src/docchunk/batching/__init__.py`
- Create: `src/docchunk/batching/builder.py`
- Create: `tests/test_batch_builder.py`

**Interfaces:**
- Produces `ReadingBatch`
- Produces:

```python
build_batches(
    atomic_texts: dict[str, str],
    counter: TokenCounter,
    policy: BatchPolicy,
    atomic_contexts: dict[str, dict[str, str]] | None = None,
) -> list[ReadingBatch]
```

- [ ] **Step 1: 写“完整 Atomic overlap”失败测试**

`tests/test_batch_builder.py`:

```python
from docchunk.batching.builder import build_batches
from docchunk.models.manifest import BatchPolicy
from docchunk.tokenizer import TokenCounter


def test_batches_overlap_by_whole_atomic_id() -> None:
    atomic_texts = {
        "A000001": "第一段。" * 20,
        "A000002": "第二段。" * 20,
        "A000003": "第三段。" * 20,
        "A000004": "第四段。" * 20,
    }
    policy = BatchPolicy(
        target_tokens=80,
        soft_min_tokens=40,
        soft_max_tokens=100,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    assert len(batches) >= 2
    assert batches[1].overlap_atomic_ids == [batches[0].atomic_ids[-1]]
    assert batches[1].atomic_ids[0] == batches[0].atomic_ids[-1]
```

- [ ] **Step 2: 写“所有新 Atomic 恰好覆盖一次”失败测试**

```python
def test_new_atomic_ids_cover_source_once() -> None:
    atomic_texts = {f"A{i:06d}": f"内容{i}。" * 10 for i in range(1, 8)}
    policy = BatchPolicy(
        target_tokens=60,
        soft_min_tokens=30,
        soft_max_tokens=80,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    new_ids = [item for batch in batches for item in batch.new_atomic_ids]
    assert new_ids == list(atomic_texts)
```

- [ ] **Step 3: 写 synthetic table header 测试**

```python
def test_table_header_context_is_marked_as_synthetic() -> None:
    atomic_texts = {
        "A000001": "| A | B |\n| --- | --- |\n| row1 | value1 |\n",
        "A000002": "| row2 | value2 |\n",
    }
    contexts = {
        "A000002": {
            "table_header": "| A | B |\n| --- | --- |\n",
        }
    }
    policy = BatchPolicy(
        target_tokens=200,
        soft_min_tokens=100,
        soft_max_tokens=240,
        overlap_atomic_count=0,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
        atomic_contexts=contexts,
    )

    assert "Synthetic Table Context" in batches[0].text
    assert "不是新的原文" in batches[0].text
    assert atomic_texts["A000002"] in batches[0].text
```

- [ ] **Step 4: 运行并确认失败**

```bash
uv run pytest tests/test_batch_builder.py -v
```

- [ ] **Step 5: 实现 `ReadingBatch`**

`src/docchunk/batching/builder.py`:

```python
from pydantic import BaseModel

from docchunk.models.manifest import BatchPolicy
from docchunk.tokenizer import TokenCounter


class ReadingBatch(BaseModel):
    batch_id: str
    atomic_ids: list[str]
    overlap_atomic_ids: list[str]
    new_atomic_ids: list[str]
    token_count: int
    text: str
```

- [ ] **Step 6: 实现 Atomic 阅读渲染**

同文件增加：

```python
def _render_atomic(
    atomic_id: str,
    text: str,
    context: dict[str, str],
) -> list[str]:
    lines = [f"## {atomic_id}", ""]

    table_header = context.get("table_header")
    if table_header:
        lines.extend(
            [
                "### Synthetic Table Context",
                "",
                "> 以下表头仅用于帮助理解跨 Atomic 表格，属于上下文提示，不是新的原文。",
                "",
                table_header.rstrip("\n"),
                "",
            ]
        )

    lines.extend([text, ""])
    return lines
```

**重要：** 这里可以重复表头，因为 Batch 是阅读视图；Atomic body 和 `index.jsonl` 没有被修改。

- [ ] **Step 7: 实现 Batch Builder**

```python
def build_batches(
    atomic_texts: dict[str, str],
    counter: TokenCounter,
    policy: BatchPolicy,
    atomic_contexts: dict[str, dict[str, str]] | None = None,
) -> list[ReadingBatch]:
    contexts = atomic_contexts or {}
    ordered_ids = list(atomic_texts)
    batches: list[ReadingBatch] = []
    cursor = 0
    previous_new_ids: list[str] = []

    while cursor < len(ordered_ids):
        overlap_ids = (
            previous_new_ids[-policy.overlap_atomic_count :]
            if batches and policy.overlap_atomic_count > 0
            else []
        )
        selected = list(overlap_ids)
        new_ids: list[str] = []

        while cursor < len(ordered_ids):
            atomic_id = ordered_ids[cursor]
            candidate_new_ids = new_ids + [atomic_id]
            candidate_rendered = _render_batch(
                batch_id=f"B{len(batches) + 1:04d}",
                overlap_ids=overlap_ids,
                new_ids=candidate_new_ids,
                atomic_texts=atomic_texts,
                contexts=contexts,
            )
            candidate_tokens = counter.count(candidate_rendered)

            if new_ids and candidate_tokens > policy.target_tokens:
                break

            selected.append(atomic_id)
            new_ids.append(atomic_id)
            cursor += 1

            if candidate_tokens >= policy.soft_max_tokens:
                break

        if not new_ids and cursor < len(ordered_ids):
            atomic_id = ordered_ids[cursor]
            selected.append(atomic_id)
            new_ids.append(atomic_id)
            cursor += 1

        batch_id = f"B{len(batches) + 1:04d}"
        rendered = _render_batch(
            batch_id=batch_id,
            overlap_ids=overlap_ids,
            new_ids=new_ids,
            atomic_texts=atomic_texts,
            contexts=contexts,
        )

        batches.append(
            ReadingBatch(
                batch_id=batch_id,
                atomic_ids=selected,
                overlap_atomic_ids=overlap_ids,
                new_atomic_ids=new_ids,
                token_count=counter.count(rendered),
                text=rendered,
            )
        )
        previous_new_ids = new_ids

    return batches
```

- [ ] **Step 8: 实现 Batch Markdown**

```python
def _render_batch(
    batch_id: str,
    overlap_ids: list[str],
    new_ids: list[str],
    atomic_texts: dict[str, str],
    contexts: dict[str, dict[str, str]],
) -> str:
    lines = [
        "---",
        f"batch_id: {batch_id}",
        "overlap_atomic_ids:",
    ]

    if overlap_ids:
        lines.extend(f"  - {item}" for item in overlap_ids)
    else:
        lines.append("  []")

    lines.append("new_atomic_ids:")
    lines.extend(f"  - {item}" for item in new_ids)
    lines.extend(["---", ""])

    if overlap_ids:
        lines.extend(
            [
                "# Context Bridge",
                "",
                "> 以下 Atomic 已在上一批读取，仅用于保持上下文连续性；"
                "下游提取器不得把它们当作新的证据再次计入。",
                "",
            ]
        )
        for item in overlap_ids:
            lines.extend(
                _render_atomic(
                    item,
                    atomic_texts[item],
                    contexts.get(item, {}),
                )
            )

    lines.extend(["# New Material", ""])
    for item in new_ids:
        lines.extend(
            _render_atomic(
                item,
                atomic_texts[item],
                contexts.get(item, {}),
            )
        )

    return "\n".join(lines)
```

- [ ] **Step 9: 增加“overlap 不消耗新内容覆盖”的测试**

```python
def test_overlap_atomic_is_not_repeated_as_new_material() -> None:
    atomic_texts = {f"A{i:06d}": ("正文。" * 20) for i in range(1, 6)}
    policy = BatchPolicy(
        target_tokens=50,
        soft_min_tokens=25,
        soft_max_tokens=70,
        overlap_atomic_count=1,
    )

    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=TokenCounter(),
        policy=policy,
    )

    for batch in batches[1:]:
        assert set(batch.overlap_atomic_ids).isdisjoint(batch.new_atomic_ids)
```

- [ ] **Step 10: 跑测试**

```bash
uv run pytest tests/test_batch_builder.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 11: 提交**

```bash
git add src/docchunk/batching tests/test_batch_builder.py
git commit -m "feat: build reading batches with whole-atomic overlap"
```

## Task 12: Pipeline：实现 `prepare`、`split`、`batch` 三个真正可用的主流程

**目标：** 第一次形成完整可运行的软件路径：

```text
输入
→ prepare：Adapter + normalized + source metadata
→ split：Atomic + index
→ batch：Reading Batches
→ manifest
```

并让以下命令真实可用：

```bash
docchunk prepare INPUT
docchunk split INPUT
docchunk batch CORPUS
```

**Files:**
- Create: `src/docchunk/pipeline.py`
- Create: `tests/test_pipeline.py`
- Modify: `src/docchunk/cli.py`
- Modify: `src/docchunk/inspect_input.py`
- Modify: `src/docchunk/storage.py`

**Interfaces:**
- Produces `make_corpus_id(title: str, source_fingerprint: str) -> str`
- Produces `prepare_corpus(input_path: Path, config: AppConfig) -> Path`
- Produces `split_prepared_corpus(corpus_path: Path, config: AppConfig) -> Path`
- Produces `batch_corpus(corpus_path: Path, config: AppConfig) -> Path`
- Produces `split_corpus(input_path: Path, config: AppConfig) -> Path`
- `split_corpus()` = `prepare_corpus()` → `split_prepared_corpus()` → `batch_corpus()`
- 多文件 Corpus 的 `char_start/char_end` 始终是 **document-relative**，不是全局坐标。

- [ ] **Step 1: 先写端到端失败测试（Markdown 单文件）**

`tests/test_pipeline.py`:

```python
import json
from pathlib import Path

from docchunk.config import AppConfig
from docchunk.pipeline import split_corpus


def small_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=100,
        atomic_soft_min_tokens=60,
        atomic_soft_max_tokens=140,
        batch_target_tokens=300,
        batch_soft_min_tokens=200,
        batch_soft_max_tokens=360,
    )


def test_split_markdown_creates_complete_corpus(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text(
        "# 第一课\n\n" + ("这是一段课程内容。" * 300),
        encoding="utf-8",
    )

    result = split_corpus(source, small_config(tmp_path / "corpora"))

    assert (result / "manifest.json").exists()
    assert (result / "index.jsonl").exists()
    assert (result / "source" / "normalized.md").exists()
    assert (result / "source" / "documents" / "D0001" / "normalized.md").exists()
    assert list((result / "atomic").glob("A*.md"))
    assert list((result / "batches").glob("B*.md"))

    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["documents"] == 1
    assert manifest["counts"]["atomic_chunks"] > 0
    assert manifest["counts"]["reading_batches"] > 0
    assert manifest["documents"][0]["document_id"] == "D0001"
```

- [ ] **Step 2: 写多文件 Document Set 失败测试**

```python
def test_directory_keeps_document_identity(tmp_path: Path) -> None:
    course = tmp_path / "course"
    course.mkdir()
    (course / "1-第一课.md").write_text("# 第一课\n\n" + "甲。" * 200, encoding="utf-8")
    (course / "2-第二课.txt").write_text("第二课。\n\n" + "乙。" * 200, encoding="utf-8")

    result = split_corpus(course, small_config(tmp_path / "corpora"))

    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert [item["document_id"] for item in manifest["documents"]] == ["D0001", "D0002"]
    assert [Path(item["source_path"]).name for item in manifest["documents"]] == [
        "1-第一课.md",
        "2-第二课.txt",
    ]

    records = [
        json.loads(line)
        for line in (result / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {"D0001", "D0002"} == {item["document_id"] for item in records}
```

- [ ] **Step 3: 写 `prepare` 不生成 Atomic 的失败测试**

```python
from docchunk.pipeline import prepare_corpus


def test_prepare_only_normalizes_sources(tmp_path: Path) -> None:
    source = tmp_path / "course.md"
    source.write_text("# 标题\n\n正文。", encoding="utf-8")

    corpus = prepare_corpus(source, small_config(tmp_path / "corpora"))

    assert (corpus / "source" / "normalized.md").exists()
    assert not list((corpus / "atomic").glob("A*.md"))
    assert not list((corpus / "batches").glob("B*.md"))
```

- [ ] **Step 4: 运行并确认失败**

```bash
uv run pytest tests/test_pipeline.py -v
```

- [ ] **Step 5: 修改 `choose_adapter`，允许传 MinerU command**

将 `src/docchunk/inspect_input.py` 改为：

```python
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pandoc import PandocAdapter
from docchunk.adapters.text import TextAdapter
from docchunk.errors import UnsupportedInputError


def choose_adapter(
    path: Path,
    mineru_command: str = "mineru",
    mineru_backend: str = "hybrid-engine",
    mineru_effort: str = "medium",
) -> DocumentAdapter:
    suffix = path.suffix.casefold()

    if suffix in {".md", ".markdown"}:
        return MarkdownAdapter()
    if suffix == ".txt":
        return TextAdapter()
    if suffix == ".docx":
        return PandocAdapter()
    if suffix == ".pdf":
        return MinerUAdapter(
            command=mineru_command,
            backend=mineru_backend,
            effort=mineru_effort,
        )

    raise UnsupportedInputError(f"Unsupported input type: {suffix or '<none>'}")
```

同步修改 Task 7 的测试调用即可；默认参数保证旧测试不需要变化。

- [ ] **Step 6: 在 storage 增加 Atomic body 读取和目录清理工具**

`src/docchunk/storage.py` 增加：

```python
import shutil


def clear_generated_files(directory: Path, pattern: str) -> None:
    for target in directory.glob(pattern):
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
```

- [ ] **Step 7: 定义稳定 Corpus fingerprint 和 corpus_id**

`src/docchunk/pipeline.py` 开头：

```python
import json
from pathlib import Path

from docchunk.adapters.base import NormalizedBlock, NormalizedDocument
from docchunk.adapters.directory import discover_inputs
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.config import AppConfig
from docchunk.errors import ExternalToolError
from docchunk.fingerprints import sha256_file, sha256_text, stable_fingerprint
from docchunk.inspect_input import choose_adapter


def make_corpus_id(title: str, source_fingerprint: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in title).strip("-").lower()
    safe = "-".join(part for part in safe.split("-") if part)
    return f"{safe[:48] or 'corpus'}-{source_fingerprint[:12]}"


def _source_inventory(input_path: Path, inputs: list[Path]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    for source in inputs:
        if input_path.is_dir():
            display_path = str(source.relative_to(input_path))
        else:
            display_path = source.name

        items.append(
            {
                "relative_path": display_path,
                "sha256": sha256_file(source),
            }
        )

    return items
```

**为什么目录不能只拿第一个文件 hash：**

如果第二课发生变化而第一课没变，Corpus 仍必须变化。因此 Corpus source fingerprint 要覆盖 **全部输入文件路径 + hash**：

```python
inventory = _source_inventory(input_path, inputs)
source_fingerprint = stable_fingerprint(inventory)
```

- [ ] **Step 8: 实现 DOCX 显式 MinerU fallback**

同文件增加：

```python
def _prepare_one_document(
    source: Path,
    config: AppConfig,
) -> NormalizedDocument:
    adapter = choose_adapter(
        source,
        mineru_command=config.mineru_command,
        mineru_backend=config.mineru_backend,
        mineru_effort=config.mineru_effort,
    )

    try:
        return adapter.prepare(source)
    except ExternalToolError:
        if source.suffix.casefold() != ".docx" or not config.docx_fallback_to_mineru:
            raise

        fallback = MinerUAdapter(command=config.mineru_command)
        document = fallback.prepare(source)
        metadata = dict(document.metadata)
        metadata["adapter_fallback"] = True
        metadata["fallback_from"] = "pandoc"
        return document.model_copy(update={"metadata": metadata})
```

**规则：**
- 默认 `docx_fallback_to_mineru=False`；
- 用户未显式开启时，Pandoc 失败就报错；
- 开启后才 fallback；
- Manifest 必须记录 `adapter_fallback=true`；
- 禁止静默切换。

- [ ] **Step 9: 实现 normalized document 持久化**

同文件增加：

```python
def _write_normalized_document(
    corpus_root: Path,
    document_id: str,
    document: NormalizedDocument,
    source_sha256: str,
) -> dict[str, object]:
    document_dir = corpus_root / "source" / "documents" / document_id
    document_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = document_dir / "normalized.md"
    normalized_path.write_text(document.text, encoding="utf-8")

    blocks_path = document_dir / "blocks.jsonl"
    with blocks_path.open("w", encoding="utf-8") as handle:
        for block in document.blocks:
            handle.write(block.model_dump_json())
            handle.write("\n")

    source_ref = {
        "source_path": str(document.source_path.resolve()),
        "source_sha256": source_sha256,
        "media_type": document.media_type,
        "adapter": document.metadata.get("adapter", "direct"),
        "adapter_fallback": bool(document.metadata.get("adapter_fallback", False)),
        "normalized_path": str(normalized_path.relative_to(corpus_root)),
        "blocks_path": str(blocks_path.relative_to(corpus_root)),
        "normalized_sha256": sha256_text(document.text),
        "metadata": document.metadata,
    }

    (document_dir / "source-ref.json").write_text(
        json.dumps(source_ref, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return source_ref
```

- [ ] **Step 10: 实现 `prepare_corpus()`**

同文件增加：

```python
from docchunk.models.manifest import (
    AtomicPolicy,
    BatchPolicy,
    CorpusCounts,
    Manifest,
    TokenizerConfig,
)
from docchunk.storage import create_corpus_layout, write_manifest
from docchunk.tokenizer import TokenCounter


def _policies_from_config(
    config: AppConfig,
) -> tuple[AtomicPolicy, BatchPolicy]:
    atomic = AtomicPolicy(
        target_tokens=config.atomic_target_tokens,
        soft_min_tokens=config.atomic_soft_min_tokens,
        soft_max_tokens=config.atomic_soft_max_tokens,
    )
    batch = BatchPolicy(
        target_tokens=config.batch_target_tokens,
        soft_min_tokens=config.batch_soft_min_tokens,
        soft_max_tokens=config.batch_soft_max_tokens,
        overlap_atomic_count=config.overlap_atomic_count,
    )
    return atomic, batch


def prepare_corpus(input_path: Path, config: AppConfig) -> Path:
    input_path = input_path.resolve()
    inputs = discover_inputs(input_path)
    if not inputs:
        raise ValueError("No supported input files found")

    inventory = _source_inventory(input_path, inputs)
    source_fingerprint = stable_fingerprint(inventory)
    title = input_path.stem if input_path.is_file() else input_path.name
    corpus_id = make_corpus_id(title, source_fingerprint)
    paths = create_corpus_layout(config.corpus_root, corpus_id)

    atomic_policy, batch_policy = _policies_from_config(config)
    documents: list[dict[str, object]] = []
    counter = TokenCounter(config.tokenizer_encoding)
    normalized_tokens = 0

    for number, source in enumerate(inputs, start=1):
        document_id = f"D{number:04d}"
        document = _prepare_one_document(source, config)
        source_hash = sha256_file(source)

        source_ref = _write_normalized_document(
            corpus_root=paths.root,
            document_id=document_id,
            document=document,
            source_sha256=source_hash,
        )
        source_ref["document_id"] = document_id
        documents.append(source_ref)
        normalized_tokens += counter.count(document.text)

    # 单文件提供一个便利入口，目录仍以 documents/Dxxxx 为权威。
    if len(documents) == 1:
        normalized_rel = str(documents[0]["normalized_path"])
        normalized_text = (paths.root / normalized_rel).read_text(encoding="utf-8")
        (paths.source_dir / "normalized.md").write_text(normalized_text, encoding="utf-8")

    manifest = Manifest(
        corpus_id=corpus_id,
        title=title,
        source_type="directory" if input_path.is_dir() else "file",
        tokenizer=TokenizerConfig(
            provider="tiktoken",
            encoding=config.tokenizer_encoding,
        ),
        atomic_policy=atomic_policy,
        batch_policy=batch_policy,
        documents=documents,
        normalization={
            "source_fingerprint": source_fingerprint,
            "input_path": str(input_path),
            "docx_fallback_to_mineru": config.docx_fallback_to_mineru,
        },
        counts=CorpusCounts(
            documents=len(documents),
            normalized_tokens=normalized_tokens,
        ),
    )
    write_manifest(paths, manifest)
    return paths.root
```

- [ ] **Step 11: 实现从磁盘恢复 NormalizedDocument**

同文件增加：

```python
def _load_prepared_document(
    corpus_root: Path,
    document_entry: dict[str, object],
) -> NormalizedDocument:
    normalized_rel = str(document_entry["normalized_path"])
    blocks_rel = str(document_entry["blocks_path"])
    text = (corpus_root / normalized_rel).read_text(encoding="utf-8")

    blocks: list[NormalizedBlock] = []
    blocks_file = corpus_root / blocks_rel
    if blocks_file.exists():
        for line in blocks_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                blocks.append(NormalizedBlock.model_validate_json(line))

    return NormalizedDocument(
        source_path=Path(str(document_entry["source_path"])),
        media_type=str(document_entry["media_type"]),
        text=text,
        blocks=blocks,
        metadata={
            "adapter": document_entry.get("adapter", "direct"),
            "adapter_fallback": document_entry.get("adapter_fallback", False),
        },
    )
```

- [ ] **Step 12: 实现 Atomic span → SourceLocation**

同文件增加：

```python
from docchunk.models.index import AtomicFlags, AtomicIndexRecord, SourceLocation
from docchunk.provenance.mineru import source_pages_for_span


def _source_location_for_chunk(
    document: NormalizedDocument,
    char_start: int,
    char_end: int,
) -> SourceLocation:
    page_start, page_end = source_pages_for_span(
        document.blocks,
        char_start=char_start,
        char_end=char_end,
    )

    overlapping_blocks = [
        block.block_index
        for block in document.blocks
        if block.char_start < char_end and block.char_end > char_start
    ]

    return SourceLocation(
        file=document.source_path.name,
        page_start=page_start,
        page_end=page_end,
        block_start=min(overlapping_blocks) if overlapping_blocks else None,
        block_end=max(overlapping_blocks) if overlapping_blocks else None,
    )
```

- [ ] **Step 13: 实现 `split_prepared_corpus()`**

```python
from docchunk.models.manifest import Manifest
from docchunk.splitting.atomic import split_atomic
from docchunk.storage import (
    append_index_record,
    write_atomic_chunk,
    write_combined_view,
)


def split_prepared_corpus(corpus_path: Path, config: AppConfig) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    counter = TokenCounter(manifest.tokenizer.encoding)

    atomic_dir = corpus_path / "atomic"
    atomic_dir.mkdir(exist_ok=True)
    for old in atomic_dir.glob("A*.md"):
        old.unlink()

    index_path = corpus_path / "index.jsonl"
    index_path.write_text("", encoding="utf-8")

    paths = create_corpus_layout(corpus_path.parent, corpus_path.name)
    global_sequence = 0
    records_for_combined: list[AtomicIndexRecord] = []

    for raw_entry in manifest.documents:
        entry = dict(raw_entry)
        document_id = str(entry["document_id"])
        document = _load_prepared_document(corpus_path, entry)

        chunks = split_atomic(
            text=document.text,
            counter=counter,
            policy=manifest.atomic_policy,
            markdown=document.media_type == "text/markdown",
        )

        for chunk in chunks:
            global_sequence += 1
            atomic_id = f"A{global_sequence:06d}"
            source_location = _source_location_for_chunk(
                document,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )

            context: dict[str, str] = {}
            if chunk.table_header_context is not None:
                context["table_header"] = chunk.table_header_context

            record = AtomicIndexRecord(
                atomic_id=atomic_id,
                document_id=document_id,
                sequence=global_sequence,
                path=f"atomic/{atomic_id}.md",
                token_count=chunk.token_count,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                heading_path=chunk.heading_path,
                source=source_location,
                flags=AtomicFlags(
                    forced_split=chunk.forced_split,
                    split_table=chunk.split_table,
                    adapter_fallback=bool(entry.get("adapter_fallback", False)),
                ),
                context=context,
            )
            write_atomic_chunk(paths, record, chunk.text)
            append_index_record(paths, record)
            records_for_combined.append(record)

    write_combined_view(paths, records_for_combined)
    manifest.counts.atomic_chunks = global_sequence
    write_manifest(paths, manifest)
    return corpus_path
```

**关键检查：**

同一个 `document_id` 内：

```text
char_start 从 0 开始
char_end 连续到该 document normalized.md 末尾
```

跨 `document_id` 时允许 `char_start` 重新从 0 开始；全局顺序由 `sequence` 和 `atomic_id` 保证。

- [ ] **Step 14: 实现读取 Index + 生成 Batch**

同文件增加：

```python
from docchunk.batching.builder import build_batches
from docchunk.storage import read_atomic_body


def _load_atomic_records(corpus_path: Path) -> list[AtomicIndexRecord]:
    records: list[AtomicIndexRecord] = []
    for line in (corpus_path / "index.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(AtomicIndexRecord.model_validate_json(line))
    return records


def batch_corpus(corpus_path: Path, config: AppConfig) -> Path:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    records = _load_atomic_records(corpus_path)
    if not records:
        raise ValueError("Corpus has no Atomic chunks; run split first")

    atomic_texts = {
        record.atomic_id: read_atomic_body(corpus_path / record.path)
        for record in records
    }
    atomic_contexts = {
        record.atomic_id: record.context
        for record in records
        if record.context
    }

    counter = TokenCounter(manifest.tokenizer.encoding)
    batches = build_batches(
        atomic_texts=atomic_texts,
        counter=counter,
        policy=manifest.batch_policy,
        atomic_contexts=atomic_contexts,
    )

    batches_dir = corpus_path / "batches"
    batches_dir.mkdir(exist_ok=True)
    for old in batches_dir.glob("B*.md"):
        old.unlink()

    for batch in batches:
        (batches_dir / f"{batch.batch_id}.md").write_text(
            batch.text,
            encoding="utf-8",
        )

    manifest.counts.reading_batches = len(batches)
    paths = create_corpus_layout(corpus_path.parent, corpus_path.name)
    write_manifest(paths, manifest)
    return corpus_path
```

- [ ] **Step 15: 实现一键 `split_corpus()`**

```python
def split_corpus(input_path: Path, config: AppConfig) -> Path:
    corpus = prepare_corpus(input_path, config)
    split_prepared_corpus(corpus, config)
    batch_corpus(corpus, config)
    return corpus
```

Task 14 会在此基础上增加“已经处理过就复用”的幂等逻辑；本 Task 先保证正确性。

- [ ] **Step 16: CLI 增加 `prepare`、`split`、`batch`**

`src/docchunk/cli.py` 使用 `Annotated` 定义必填参数，避免在命令签名里使用 Ellipsis：

```python
from pathlib import Path
from typing import Annotated

import typer

from docchunk.config import AppConfig
from docchunk.pipeline import batch_corpus, prepare_corpus, split_corpus


ExistingPath = Annotated[Path, typer.Argument(exists=True, readable=True)]


@app.command()
def prepare(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
) -> None:
    """Normalize input files without creating Atomic chunks."""
    config = AppConfig()
    if corpus_root is not None:
        config = config.model_copy(update={"corpus_root": corpus_root})

    typer.echo(str(prepare_corpus(input_path, config)))


@app.command()
def split(
    input_path: ExistingPath,
    corpus_root: Annotated[Path | None, typer.Option("--corpus-root")] = None,
) -> None:
    """Prepare, split, and batch a long-document corpus."""
    config = AppConfig()
    if corpus_root is not None:
        config = config.model_copy(update={"corpus_root": corpus_root})

    typer.echo(str(split_corpus(input_path, config)))


@app.command("batch")
def batch_command(
    corpus_path: ExistingPath,
) -> None:
    """Build reading batches from an existing Atomic corpus."""
    typer.echo(str(batch_corpus(corpus_path, AppConfig())))
```

- [ ] **Step 17: 跑 Pipeline 测试**

```bash
uv run pytest tests/test_pipeline.py tests/test_cli_smoke.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 18: 手工 smoke test**

```bash
rm -rf /tmp/docchunk-demo /tmp/docchunk-corpora
mkdir -p /tmp/docchunk-demo

python - <<'PY'
from pathlib import Path
Path("/tmp/docchunk-demo/course.md").write_text(
    "# 第一课\n\n" + "这是课程逐字稿。这里继续解释。" * 2000,
    encoding="utf-8",
)
PY

CORPUS="$(uv run docchunk split /tmp/docchunk-demo/course.md \
  --corpus-root /tmp/docchunk-corpora)"

printf '%s\n' "$CORPUS"
find "$CORPUS" -maxdepth 3 -type f | sort | head -30
```

Expected 至少看到：

```text
manifest.json
index.jsonl
combined.md
source/normalized.md
source/documents/D0001/normalized.md
source/documents/D0001/blocks.jsonl
source/documents/D0001/source-ref.json
atomic/A000001.md
batches/B0001.md
```

- [ ] **Step 19: 单独测试 `prepare`**

```bash
PREPARED="$(uv run docchunk prepare /tmp/docchunk-demo/course.md \
  --corpus-root /tmp/docchunk-prepared)"

find "$PREPARED/atomic" -name 'A*.md'
find "$PREPARED/batches" -name 'B*.md'
```

Expected: 两个 `find` 都没有输出。

- [ ] **Step 20: 单独测试 `batch`**

先对已 split 的 Corpus 删除 Batch：

```bash
rm -f "$CORPUS"/batches/B*.md
uv run docchunk batch "$CORPUS"
find "$CORPUS/batches" -name 'B*.md' | head
```

Expected: Batch 文件重新出现，Atomic 没有变化。

- [ ] **Step 21: 提交**

```bash
git add src/docchunk/pipeline.py \
        src/docchunk/cli.py \
        src/docchunk/inspect_input.py \
        src/docchunk/storage.py \
        tests/test_pipeline.py
git commit -m "feat: wire prepare split and batch pipelines"
```

## Task 13: `verify` — 按 Document 重建原文、校验 Batch 覆盖与 provenance

**目标：** `verify` 是 V1 的核心安全网。任何切漏、切重、offset 断裂、Atomic 文件缺失、Batch 新内容重复、overlap 错误、normalized 被篡改，都必须被发现。多文件 Corpus 必须按 `document_id` 分别重建，不能把第二个文件的 `char_start=0` 错判为断裂。

**Files:**
- Create: `src/docchunk/verify.py`
- Create: `tests/test_verify.py`
- Modify: `src/docchunk/cli.py`
- Modify: `src/docchunk/pipeline.py`

**Interfaces:**
- Produces `VerificationReport`
- Produces `verify_corpus(corpus_path: Path, persist: bool = True) -> VerificationReport`
- `docchunk split` 在 Task 13 完成后默认自动 verify；verify 失败时 CLI exit code = 1。

- [ ] **Step 1: 写“新 Corpus 必须 PASS”测试**

`tests/test_verify.py`:

```python
from pathlib import Path

from docchunk.config import AppConfig
from docchunk.pipeline import split_corpus
from docchunk.verify import verify_corpus


def verify_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=80,
        atomic_soft_min_tokens=40,
        atomic_soft_max_tokens=100,
        batch_target_tokens=200,
        batch_soft_min_tokens=120,
        batch_soft_max_tokens=240,
    )


def test_verify_passes_for_fresh_corpus(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# 标题\n\n" + ("完整内容。" * 500), encoding="utf-8")

    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))
    report = verify_corpus(corpus)

    assert report.ok is True
    assert report.errors == []
```

- [ ] **Step 2: 写“多文件 document-relative offset 必须 PASS”测试**

```python
def test_verify_handles_document_relative_offsets(tmp_path: Path) -> None:
    course = tmp_path / "course"
    course.mkdir()
    (course / "1.md").write_text("# 一\n\n" + "甲。" * 300, encoding="utf-8")
    (course / "2.md").write_text("# 二\n\n" + "乙。" * 300, encoding="utf-8")

    corpus = split_corpus(course, verify_config(tmp_path / "corpora"))
    report = verify_corpus(corpus)

    assert report.ok is True
```

- [ ] **Step 3: 写“删除 Atomic 必须 FAIL”测试**

```python
def test_verify_fails_when_atomic_file_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 500, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    first_atomic = sorted((corpus / "atomic").glob("A*.md"))[0]
    first_atomic.unlink()

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("missing atomic file" in error.lower() for error in report.errors)
```

- [ ] **Step 4: 写“篡改 Atomic 正文必须 FAIL”测试**

```python
def test_verify_fails_when_atomic_body_changes(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 500, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    first_atomic = sorted((corpus / "atomic").glob("A*.md"))[0]
    original = first_atomic.read_text(encoding="utf-8")
    first_atomic.write_text(original + "被篡改", encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
    assert any("reconstructed text" in error.lower() for error in report.errors)
```

- [ ] **Step 5: 写“Batch new_atomic_ids 重复必须 FAIL”测试**

```python
def test_verify_fails_when_batch_new_material_is_duplicated(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("正文。" * 800, encoding="utf-8")
    corpus = split_corpus(source, verify_config(tmp_path / "corpora"))

    batches = sorted((corpus / "batches").glob("B*.md"))
    assert len(batches) >= 2

    second = batches[1]
    content = second.read_text(encoding="utf-8")
    first_new_line = next(
        line for line in content.splitlines()
        if line.startswith("  - A")
    )
    content = content.replace(
        "new_atomic_ids:\n",
        f"new_atomic_ids:\n{first_new_line}\n",
        1,
    )
    second.write_text(content, encoding="utf-8")

    report = verify_corpus(corpus)
    assert report.ok is False
```

- [ ] **Step 6: 运行并确认失败**

```bash
uv run pytest tests/test_verify.py -v
```

- [ ] **Step 7: 实现 `VerificationReport` 和读取工具**

`src/docchunk/verify.py`:

```python
import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from docchunk.fingerprints import sha256_text
from docchunk.models.index import AtomicIndexRecord
from docchunk.models.manifest import Manifest, utc_now_iso
from docchunk.storage import read_atomic_body
from docchunk.tokenizer import TokenCounter


class VerificationReport(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _load_records(corpus_path: Path) -> list[AtomicIndexRecord]:
    index_path = corpus_path / "index.jsonl"
    records: list[AtomicIndexRecord] = []

    for line_number, line in enumerate(
        index_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            records.append(AtomicIndexRecord.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid index.jsonl line {line_number}: {exc}") from exc

    return records


def _batch_id_lists(path: Path) -> tuple[list[str], list[str]]:
    overlap: list[str] = []
    new: list[str] = []
    section: str | None = None
    fence_count = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "---":
            fence_count += 1
            if fence_count >= 2:
                break
            continue

        if line == "overlap_atomic_ids:":
            section = "overlap"
            continue
        if line == "new_atomic_ids:":
            section = "new"
            continue

        if line.startswith("  - A"):
            atomic_id = line[4:].strip()
            if section == "overlap":
                overlap.append(atomic_id)
            elif section == "new":
                new.append(atomic_id)

    return overlap, new
```

- [ ] **Step 8: 实现 Manifest/Index 基础检查**

同文件实现 `verify_corpus()` 的开头：

```python
def verify_corpus(
    corpus_path: Path,
    persist: bool = True,
) -> VerificationReport:
    corpus_path = corpus_path.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = corpus_path / "manifest.json"
    index_path = corpus_path / "index.jsonl"

    if not manifest_path.exists():
        return VerificationReport(
            ok=False,
            errors=["Missing manifest.json"],
        )
    if not index_path.exists():
        return VerificationReport(
            ok=False,
            errors=["Missing index.jsonl"],
        )

    try:
        manifest = Manifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        return VerificationReport(
            ok=False,
            errors=[f"Invalid manifest.json: {exc}"],
        )

    try:
        records = _load_records(corpus_path)
    except ValueError as exc:
        return VerificationReport(ok=False, errors=[str(exc)])

    expected_sequences = list(range(1, len(records) + 1))
    actual_sequences = [record.sequence for record in records]
    if actual_sequences != expected_sequences:
        errors.append(
            "Atomic sequence is not contiguous from 1 to N"
        )

    expected_ids = [f"A{number:06d}" for number in expected_sequences]
    actual_ids = [record.atomic_id for record in records]
    if actual_ids != expected_ids:
        errors.append("Atomic IDs do not match sequence order")
```

- [ ] **Step 9: 实现 Atomic 文件、token 和 document-relative offset 检查**

继续：

```python
    counter = TokenCounter(manifest.tokenizer.encoding)
    by_document: dict[str, list[AtomicIndexRecord]] = defaultdict(list)

    for record in records:
        by_document[record.document_id].append(record)

        atomic_path = corpus_path / record.path
        if not atomic_path.exists():
            errors.append(f"Missing atomic file: {record.path}")
            continue

        body = read_atomic_body(atomic_path)
        actual_tokens = counter.count(body)
        if actual_tokens != record.token_count:
            errors.append(
                f"Token count mismatch for {record.atomic_id}: "
                f"index={record.token_count}, actual={actual_tokens}"
            )

        if record.char_end < record.char_start:
            errors.append(
                f"Invalid char range for {record.atomic_id}: "
                f"{record.char_start}>{record.char_end}"
            )

        if len(body) != record.char_end - record.char_start:
            errors.append(
                f"Character length mismatch for {record.atomic_id}"
            )
```

- [ ] **Step 10: 按每个 Document 重建 normalized source**

继续：

```python
    document_entries = {
        str(item["document_id"]): dict(item)
        for item in manifest.documents
    }

    for document_id, document_records in by_document.items():
        entry = document_entries.get(document_id)
        if entry is None:
            errors.append(f"Index references unknown document: {document_id}")
            continue

        normalized_path = corpus_path / str(entry["normalized_path"])
        if not normalized_path.exists():
            errors.append(
                f"Missing normalized document for {document_id}: "
                f"{entry['normalized_path']}"
            )
            continue

        normalized = normalized_path.read_text(encoding="utf-8")
        reconstructed_parts: list[str] = []
        expected_start = 0

        for record in document_records:
            if record.char_start != expected_start:
                errors.append(
                    f"Non-contiguous char offsets in {document_id}: "
                    f"expected {expected_start}, got {record.char_start} "
                    f"at {record.atomic_id}"
                )

            atomic_path = corpus_path / record.path
            if atomic_path.exists():
                reconstructed_parts.append(read_atomic_body(atomic_path))

            expected_start = record.char_end

        reconstructed = "".join(reconstructed_parts)
        if reconstructed != normalized:
            errors.append(
                f"Reconstructed text does not match normalized source for {document_id}"
            )

        if document_records and document_records[-1].char_end != len(normalized):
            errors.append(
                f"Final char_end does not reach normalized source end for {document_id}"
            )

        expected_normalized_hash = entry.get("normalized_sha256")
        if isinstance(expected_normalized_hash, str):
            actual_hash = sha256_text(normalized)
            if actual_hash != expected_normalized_hash:
                errors.append(
                    f"Normalized source hash mismatch for {document_id}"
                )
```

- [ ] **Step 11: 实现 Batch 覆盖和 overlap 检查**

继续：

```python
    batch_files = sorted((corpus_path / "batches").glob("B*.md"))
    all_new_ids: list[str] = []
    previous_new_ids: list[str] = []

    for batch_index, batch_path in enumerate(batch_files):
        overlap_ids, new_ids = _batch_id_lists(batch_path)

        for atomic_id in overlap_ids + new_ids:
            if atomic_id not in actual_ids:
                errors.append(
                    f"{batch_path.name} references unknown Atomic {atomic_id}"
                )

        if set(overlap_ids) & set(new_ids):
            errors.append(
                f"{batch_path.name} contains the same Atomic as overlap and new material"
            )

        if len(new_ids) != len(set(new_ids)):
            errors.append(
                f"{batch_path.name} contains duplicate new_atomic_ids"
            )

        expected_overlap = (
            previous_new_ids[-manifest.batch_policy.overlap_atomic_count :]
            if batch_index > 0 and manifest.batch_policy.overlap_atomic_count > 0
            else []
        )
        if overlap_ids != expected_overlap:
            errors.append(
                f"{batch_path.name} overlap does not match previous Batch tail"
            )

        all_new_ids.extend(new_ids)
        previous_new_ids = new_ids

        batch_tokens = counter.count(batch_path.read_text(encoding="utf-8"))
        if batch_tokens > manifest.batch_policy.soft_max_tokens:
            warnings.append(
                f"{batch_path.name} has {batch_tokens} tokens, above "
                f"batch soft max {manifest.batch_policy.soft_max_tokens}"
            )

    if all_new_ids != actual_ids:
        errors.append(
            "Batch new_atomic_ids do not cover all Atomic IDs exactly once and in order"
        )
```

- [ ] **Step 12: 实现 provenance 与 forced split warnings**

继续：

```python
    if records:
        forced_count = sum(record.flags.forced_split for record in records)
        forced_ratio = forced_count / len(records)
        if forced_ratio > 0.05:
            warnings.append(
                f"Forced split ratio is {forced_ratio:.1%}; inspect OCR/text quality"
            )

    for entry in manifest.documents:
        entry_dict = dict(entry)
        source_path = str(entry_dict.get("source_path", ""))
        if not source_path.lower().endswith(".pdf"):
            continue

        document_id = str(entry_dict["document_id"])
        pdf_records = by_document.get(document_id, [])
        if pdf_records and not any(
            record.source.page_start is not None
            for record in pdf_records
        ):
            warnings.append(
                f"PDF document {document_id} has no page provenance"
            )

        metadata = entry_dict.get("metadata")
        if isinstance(metadata, dict):
            unaligned = metadata.get("unaligned_blocks")
            if isinstance(unaligned, int) and unaligned > 0:
                warnings.append(
                    f"{document_id} has {unaligned} MinerU blocks that "
                    "could not be aligned to normalized Markdown"
                )
```

- [ ] **Step 13: 更新 Manifest verification 状态并返回**

最后：

```python
    ok = not errors

    if persist:
        manifest.verification.status = "passed" if ok else "failed"
        manifest.verification.checked_at = utc_now_iso()
        manifest.verification.errors = errors
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return VerificationReport(
        ok=ok,
        errors=errors,
        warnings=warnings,
    )
```

- [ ] **Step 14: CLI 增加 `verify`**

`src/docchunk/cli.py`：

```python
from docchunk.verify import verify_corpus


@app.command()
def verify(corpus_path: ExistingPath) -> None:
    """Verify corpus integrity, provenance, and Batch coverage."""
    report = verify_corpus(corpus_path)

    for warning in report.warnings:
        typer.echo(f"WARNING: {warning}")

    if report.ok:
        typer.echo("PASS")
        return

    for error in report.errors:
        typer.echo(f"ERROR: {error}", err=True)
    raise typer.Exit(code=1)
```

- [ ] **Step 15: `split` 命令完成后自动 verify**

在 `split()` 中把：

```python
typer.echo(str(split_corpus(input_path, config)))
```

改为：

```python
result = split_corpus(input_path, config)
report = verify_corpus(result)

if not report.ok:
    for error in report.errors:
        typer.echo(f"ERROR: {error}", err=True)
    raise typer.Exit(code=1)

for warning in report.warnings:
    typer.echo(f"WARNING: {warning}")

typer.echo(str(result))
```

这样日常 `docchunk split` 的输出路径只会在完整性验证通过后返回。

- [ ] **Step 16: 跑测试**

```bash
uv run pytest tests/test_verify.py tests/test_pipeline.py -v
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 17: 手工破坏测试**

```bash
CORPUS="$(uv run docchunk split \
  /tmp/docchunk-demo/course.md \
  --corpus-root /tmp/docchunk-corpora)"

uv run docchunk verify "$CORPUS"
```

Expected:

```text
PASS
```

复制后破坏：

```bash
rm -rf /tmp/broken-corpus
cp -R "$CORPUS" /tmp/broken-corpus
FIRST_ATOMIC="$(find /tmp/broken-corpus/atomic -name 'A*.md' | sort | head -1)"
rm "$FIRST_ATOMIC"

uv run docchunk verify /tmp/broken-corpus
printf 'exit=%s\n' "$?"
```

Expected:
- 输出含 `Missing atomic file`；
- exit code 非 0。

- [ ] **Step 18: 提交**

```bash
git add src/docchunk/verify.py \
        src/docchunk/cli.py \
        src/docchunk/pipeline.py \
        tests/test_verify.py
git commit -m "feat: verify corpus integrity provenance and batch coverage"
```

## Task 14: State、幂等、Fingerprint、`status` 与 `rebuild-batches`

**目标：** 同一原文不重复 OCR/Pandoc；Atomic policy 不变就不重切；只改 Batch 参数时只重建 Batch；失败状态可见；用户可以显式 `--force` 重跑，而不是程序偷偷覆盖。

**Files:**
- Modify: `src/docchunk/models/manifest.py`
- Modify: `src/docchunk/models/state.py`
- Modify: `src/docchunk/pipeline.py`
- Modify: `src/docchunk/cli.py`
- Create: `tests/test_state_resume.py`

**Interfaces:**
- Adds `CorpusFingerprints`
- Adds `load_state(corpus_path) -> CorpusState`
- Adds `write_state(corpus_path, state) -> None`
- Updates:
  - `prepare_corpus(input_path, config, force=False)`
  - `split_prepared_corpus(corpus_path, config, force=False)`
  - `batch_corpus(corpus_path, config, force=False)`
  - `split_corpus(input_path, config, force=False)`
- Produces `rebuild_batches(corpus_path, target_tokens, soft_min_tokens, soft_max_tokens, overlap_atomic_count) -> Path`
- Produces CLI:
  - `docchunk status CORPUS`
  - `docchunk rebuild-batches CORPUS --target-tokens 32000 --soft-min-tokens 20000 --soft-max-tokens 40000 --overlap-atomic-count 1`

- [ ] **Step 1: 写“第二次 split 不再调用 Adapter”失败测试**

`tests/test_state_resume.py`:

```python
from pathlib import Path
from unittest.mock import patch

from docchunk.config import AppConfig
from docchunk.pipeline import split_corpus


def reuse_config(root: Path) -> AppConfig:
    return AppConfig(
        corpus_root=root,
        atomic_target_tokens=80,
        atomic_soft_min_tokens=40,
        atomic_soft_max_tokens=100,
        batch_target_tokens=200,
        batch_soft_min_tokens=120,
        batch_soft_max_tokens=240,
    )


def test_second_split_reuses_prepared_source(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("内容。" * 500, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")

    first = split_corpus(source, config)

    # pipeline.py 在 Task 12 直接 import 了 choose_adapter，
    # 所以 patch 必须打在 docchunk.pipeline.choose_adapter。
    with patch("docchunk.pipeline.choose_adapter") as choose:
        second = split_corpus(source, config)

    assert second == first
    choose.assert_not_called()
```

- [ ] **Step 2: 写“rebuild Batch 不改变 Atomic bytes”失败测试**

```python
from docchunk.pipeline import rebuild_batches


def test_rebuild_batches_does_not_touch_atomic_files(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("内容。" * 1200, encoding="utf-8")
    config = reuse_config(tmp_path / "corpora")
    corpus = split_corpus(source, config)

    before = {
        item.name: item.read_bytes()
        for item in sorted((corpus / "atomic").glob("A*.md"))
    }

    rebuild_batches(
        corpus_path=corpus,
        target_tokens=260,
        soft_min_tokens=160,
        soft_max_tokens=320,
        overlap_atomic_count=1,
    )

    after = {
        item.name: item.read_bytes()
        for item in sorted((corpus / "atomic").glob("A*.md"))
    }

    assert after == before
```

- [ ] **Step 3: 写“source 改变产生新 Corpus”测试**

```python
def test_changed_source_creates_new_corpus_id(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    config = reuse_config(tmp_path / "corpora")

    source.write_text("版本一。" * 300, encoding="utf-8")
    first = split_corpus(source, config)

    source.write_text("版本二。" * 300, encoding="utf-8")
    second = split_corpus(source, config)

    assert first != second
    assert first.exists()
    assert second.exists()
```

- [ ] **Step 4: 写 State 失败状态测试**

```python
from docchunk.models.state import ProcessingStage
from docchunk.pipeline import load_state


def test_failed_pipeline_records_failed_state(tmp_path: Path) -> None:
    source = tmp_path / "bad.docx"
    source.write_bytes(b"not-a-real-docx")
    config = reuse_config(tmp_path / "corpora")

    with patch("docchunk.pipeline._prepare_one_document", side_effect=RuntimeError("boom")):
        try:
            split_corpus(source, config)
        except RuntimeError:
            pass

    corpus_dirs = list((tmp_path / "corpora").glob("*"))
    assert len(corpus_dirs) == 1
    state = load_state(corpus_dirs[0])
    assert state.stage is ProcessingStage.FAILED
    assert "boom" in (state.error or "")
```

- [ ] **Step 5: 运行并确认失败**

```bash
uv run pytest tests/test_state_resume.py -v
```

- [ ] **Step 6: 在 Manifest 增加 Fingerprints 模型**

修改 `src/docchunk/models/manifest.py`：

```python
class CorpusFingerprints(BaseModel):
    source: str = ""
    normalization: str = ""
    atomic_policy: str = ""
    batch_policy: str = ""
```

在 `Manifest` 增加：

```python
fingerprints: CorpusFingerprints = Field(default_factory=CorpusFingerprints)
```

并在 `src/docchunk/models/__init__.py` 导出 `CorpusFingerprints`。

- [ ] **Step 7: 定义四种 fingerprint**

在 `pipeline.py` 增加：

```python
from importlib.metadata import PackageNotFoundError, version as package_version

from docchunk.models.manifest import CorpusFingerprints


def _installed_version(package: str) -> str:
    try:
        return package_version(package)
    except PackageNotFoundError:
        return "not-installed"


def _normalization_fingerprint(config: AppConfig) -> str:
    return stable_fingerprint(
        {
            "docx_adapter": "pandoc",
            "pdf_adapter": "mineru",
            "docx_fallback_to_mineru": config.docx_fallback_to_mineru,
        }
    )


def _atomic_policy_fingerprint(
    manifest: Manifest,
) -> str:
    return stable_fingerprint(
        {
            "tokenizer": manifest.tokenizer.model_dump(),
            "atomic_policy": manifest.atomic_policy.model_dump(),
            "splitter_backend": "semantic-text-splitter",
            "splitter_version": _installed_version("semantic-text-splitter"),
            "schema_version": manifest.schema_version,
        }
    )


def _batch_policy_fingerprint(
    manifest: Manifest,
) -> str:
    return stable_fingerprint(
        {
            "batch_policy": manifest.batch_policy.model_dump(),
            "batch_renderer": "v1",
            "schema_version": manifest.schema_version,
        }
    )
```

**注意：**
- MinerU/Pandoc 升级不会自动让既有 Corpus 失效；
- 既有 normalized source 本身就是可验证资产；
- 如果用户希望用新版本重新转换，使用 `--force`；
- splitter 版本会影响 Atomic 切点，因此进入 Atomic fingerprint。

- [ ] **Step 8: 实现 `state.json` 读写**

在 `pipeline.py` 增加：

```python
from docchunk.models.state import CorpusState, ProcessingStage


def load_state(corpus_path: Path) -> CorpusState:
    state_path = corpus_path / "state.json"
    if not state_path.exists():
        return CorpusState()
    return CorpusState.model_validate_json(
        state_path.read_text(encoding="utf-8")
    )


def write_state(corpus_path: Path, state: CorpusState) -> None:
    (corpus_path / "state.json").write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _set_stage(
    corpus_path: Path,
    stage: ProcessingStage,
    *,
    error: str | None = None,
) -> None:
    state = load_state(corpus_path)
    state.stage = stage
    state.error = error
    write_state(corpus_path, state)
```

- [ ] **Step 9: 修改 `prepare_corpus()`：先计算路径，再判断能否复用**

在创建 `paths` 后、调用 Adapter 前：

```python
    atomic_policy, batch_policy = _policies_from_config(config)
    normalization_fp = _normalization_fingerprint(config)

    if paths.manifest_json.exists() and not force:
        existing = Manifest.model_validate_json(
            paths.manifest_json.read_text(encoding="utf-8")
        )
        if (
            existing.fingerprints.source == source_fingerprint
            and existing.fingerprints.normalization == normalization_fp
        ):
            # prepare 阶段可以复用 normalized source，但要把“本次请求的”
            # Atomic/Batch policy 写回 Manifest。后续阶段通过 fingerprint
            # 判断是否只重切 Atomic 或只重建 Batch。
            existing.atomic_policy = atomic_policy
            existing.batch_policy = batch_policy
            write_manifest(paths, existing)
            return paths.root

    _set_stage(paths.root, ProcessingStage.PREPARING)
```

因此函数签名改为：

```python
def prepare_corpus(
    input_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
```

创建新 Manifest 时：

```python
fingerprints=CorpusFingerprints(
    source=source_fingerprint,
    normalization=normalization_fp,
),
```

成功写完后：

```python
_set_stage(paths.root, ProcessingStage.PREPARED)
```

- [ ] **Step 10: `prepare_corpus()` 失败必须写 FAILED**

先把 Task 12 中的 document 循环抽成一个明确 helper，避免在 try/except 里复制逻辑：

```python
def _prepare_documents(
    paths,
    inputs: list[Path],
    config: AppConfig,
    counter: TokenCounter,
) -> tuple[list[dict[str, object]], int]:
    documents: list[dict[str, object]] = []
    normalized_tokens = 0

    for number, source in enumerate(inputs, start=1):
        document_id = f"D{number:04d}"
        document = _prepare_one_document(source, config)
        source_hash = sha256_file(source)

        source_ref = _write_normalized_document(
            corpus_root=paths.root,
            document_id=document_id,
            document=document,
            source_sha256=source_hash,
        )
        source_ref["document_id"] = document_id
        documents.append(source_ref)
        normalized_tokens += counter.count(document.text)

    return documents, normalized_tokens
```

然后 `prepare_corpus()` 使用：

```python
    try:
        documents, normalized_tokens = _prepare_documents(
            paths=paths,
            inputs=inputs,
            config=config,
            counter=counter,
        )
    except Exception as exc:
        _set_stage(
            paths.root,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
```

后续继续使用 `documents` 和 `normalized_tokens` 构造 Manifest。这样失败状态管理只有一处，转换逻辑也只有一份。

- [ ] **Step 11: 修改 Atomic 复用**

`split_prepared_corpus()` 签名：

```python
def split_prepared_corpus(
    corpus_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
```

读取 Manifest 后：

```python
    expected_atomic_fp = _atomic_policy_fingerprint(manifest)

    atomic_files = list((corpus_path / "atomic").glob("A*.md"))
    if (
        not force
        and manifest.fingerprints.atomic_policy == expected_atomic_fp
        and (corpus_path / "index.jsonl").exists()
        and atomic_files
    ):
        return corpus_path

    manifest.verification.status = "pending"
    manifest.verification.checked_at = None
    manifest.verification.errors = []
    write_manifest(
        create_corpus_layout(corpus_path.parent, corpus_path.name),
        manifest,
    )
    _set_stage(corpus_path, ProcessingStage.SPLITTING)
```

成功后：

```python
manifest.fingerprints.atomic_policy = expected_atomic_fp
write_manifest(paths, manifest)
_set_stage(corpus_path, ProcessingStage.SPLIT)
```

失败则：

```python
_set_stage(
    corpus_path,
    ProcessingStage.FAILED,
    error=f"{type(exc).__name__}: {exc}",
)
raise
```

- [ ] **Step 12: 修改 Batch 复用**

`batch_corpus()` 签名：

```python
def batch_corpus(
    corpus_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
```

读取 manifest 后：

```python
    expected_batch_fp = _batch_policy_fingerprint(manifest)
    batch_files = list((corpus_path / "batches").glob("B*.md"))

    if (
        not force
        and manifest.fingerprints.batch_policy == expected_batch_fp
        and batch_files
    ):
        return corpus_path

    manifest.verification.status = "pending"
    manifest.verification.checked_at = None
    manifest.verification.errors = []
    write_manifest(
        create_corpus_layout(corpus_path.parent, corpus_path.name),
        manifest,
    )
    _set_stage(corpus_path, ProcessingStage.BATCHING)
```

生成成功后：

```python
manifest.fingerprints.batch_policy = expected_batch_fp
write_manifest(paths, manifest)
_set_stage(corpus_path, ProcessingStage.BATCHED)
```

- [ ] **Step 13: 修改 `split_corpus()`**

签名：

```python
def split_corpus(
    input_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
```

实现：

```python
def split_corpus(
    input_path: Path,
    config: AppConfig,
    force: bool = False,
) -> Path:
    corpus = prepare_corpus(input_path, config, force=force)

    try:
        split_prepared_corpus(corpus, config, force=force)
        batch_corpus(corpus, config, force=force)
        return corpus
    except Exception as exc:
        _set_stage(
            corpus,
            ProcessingStage.FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
```

`verify` 成功后，Task 13 的 CLI 或 verify 持久化阶段将 state 设为 `READY`。在 `verify_corpus()` PASS 分支追加：

```python
from docchunk.models.state import CorpusState, ProcessingStage

state_path = corpus_path / "state.json"
state = (
    CorpusState.model_validate_json(state_path.read_text(encoding="utf-8"))
    if state_path.exists()
    else CorpusState()
)
state.stage = ProcessingStage.READY if ok else ProcessingStage.FAILED
state.error = None if ok else "Corpus verification failed"
state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 14: 实现 `rebuild_batches()`**

在 `pipeline.py` 增加：

```python
from docchunk.models.manifest import BatchPolicy


def rebuild_batches(
    corpus_path: Path,
    target_tokens: int,
    soft_min_tokens: int,
    soft_max_tokens: int,
    overlap_atomic_count: int,
) -> Path:
    corpus_path = corpus_path.resolve()
    manifest_path = corpus_path / "manifest.json"
    manifest = Manifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    if not (0 < soft_min_tokens <= target_tokens <= soft_max_tokens):
        raise ValueError(
            "Batch token values must satisfy: "
            "0 < soft_min <= target <= soft_max"
        )

    manifest.batch_policy = BatchPolicy(
        target_tokens=target_tokens,
        soft_min_tokens=soft_min_tokens,
        soft_max_tokens=soft_max_tokens,
        overlap_atomic_count=overlap_atomic_count,
    )
    manifest.fingerprints.batch_policy = ""
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )

    result = batch_corpus(
        corpus_path,
        AppConfig(),
        force=True,
    )

    from docchunk.verify import verify_corpus

    report = verify_corpus(result)
    if not report.ok:
        raise RuntimeError(
            "Rebuilt batches failed verification: "
            + "; ".join(report.errors)
        )
    return result
```

- [ ] **Step 15: 实现 `status` 输出函数**

在 `pipeline.py` 增加：

```python
def corpus_status(corpus_path: Path) -> dict[str, object]:
    corpus_path = corpus_path.resolve()
    manifest = Manifest.model_validate_json(
        (corpus_path / "manifest.json").read_text(encoding="utf-8")
    )
    state = load_state(corpus_path)

    return {
        "corpus_id": manifest.corpus_id,
        "stage": state.stage.value,
        "documents": manifest.counts.documents,
        "atomic_chunks": manifest.counts.atomic_chunks,
        "reading_batches": manifest.counts.reading_batches,
        "verification": manifest.verification.status,
        "source_fingerprint": manifest.fingerprints.source,
        "tokenizer": manifest.tokenizer.encoding,
        "atomic_policy": manifest.atomic_policy.model_dump(),
        "batch_policy": manifest.batch_policy.model_dump(),
        "last_error": state.error,
    }
```

- [ ] **Step 16: CLI 增加 `--force`、`status`、`rebuild-batches`**

给 `prepare` 和 `split` 增加：

```python
force: Annotated[
    bool,
    typer.Option("--force", help="Regenerate reusable stages even if fingerprints match."),
] = False
```

调用时传 `force=force`。

`status`：

```python
from rich.console import Console
from rich.table import Table

from docchunk.pipeline import corpus_status, rebuild_batches

console = Console()


@app.command()
def status(corpus_path: ExistingPath) -> None:
    """Show corpus processing state and active policies."""
    data = corpus_status(corpus_path)
    table = Table(title="docchunk corpus status")
    table.add_column("Field")
    table.add_column("Value")

    for key, value in data.items():
        table.add_row(key, str(value))

    console.print(table)
```

`rebuild-batches`：

```python
@app.command("rebuild-batches")
def rebuild_batches_command(
    corpus_path: ExistingPath,
    target_tokens: Annotated[int, typer.Option("--target-tokens")] = 24000,
    soft_min_tokens: Annotated[int, typer.Option("--soft-min-tokens")] = 16000,
    soft_max_tokens: Annotated[int, typer.Option("--soft-max-tokens")] = 32000,
    overlap_atomic_count: Annotated[
        int,
        typer.Option("--overlap-atomic-count"),
    ] = 1,
) -> None:
    """Rebuild only reading batches; never regenerate Atomic chunks."""
    result = rebuild_batches(
        corpus_path=corpus_path,
        target_tokens=target_tokens,
        soft_min_tokens=soft_min_tokens,
        soft_max_tokens=soft_max_tokens,
        overlap_atomic_count=overlap_atomic_count,
    )
    typer.echo(str(result))
```

- [ ] **Step 17: 验证 Atomic bytes 不变**

```bash
CORPUS="$(uv run docchunk split \
  /tmp/docchunk-demo/course.md \
  --corpus-root /tmp/docchunk-corpora)"

find "$CORPUS/atomic" -name 'A*.md' -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > /tmp/atomic-before.sha256

uv run docchunk rebuild-batches "$CORPUS" \
  --target-tokens 32000 \
  --soft-min-tokens 20000 \
  --soft-max-tokens 40000 \
  --overlap-atomic-count 1

find "$CORPUS/atomic" -name 'A*.md' -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > /tmp/atomic-after.sha256

diff -u /tmp/atomic-before.sha256 /tmp/atomic-after.sha256
```

Expected: `diff` 没有任何输出。

- [ ] **Step 18: 跑测试**

```bash
uv run pytest tests/test_state_resume.py tests/test_verify.py -v
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 19: 提交**

```bash
git add src/docchunk/models \
        src/docchunk/pipeline.py \
        src/docchunk/cli.py \
        src/docchunk/verify.py \
        tests/test_state_resume.py
git commit -m "feat: add corpus fingerprints idempotence and batch rebuilding"
```

## Task 15: `doctor`、`inspect`、错误日志和新手友好提示

**目标：** 用户不需要自己猜 MinerU/Pandoc/Python 哪个坏了。

**Files:**
- Create: `src/docchunk/doctor.py`
- Create: `src/docchunk/logging_utils.py`
- Create: `tests/test_doctor.py`
- Modify: `src/docchunk/cli.py`

**Interfaces:**
- `docchunk doctor`
- `docchunk inspect INPUT`

- [ ] **Step 1: 写 doctor 测试**

```python
from unittest.mock import patch

from docchunk.doctor import run_doctor


def test_doctor_reports_missing_pandoc() -> None:
    with patch("shutil.which") as which:
        which.side_effect = lambda name: None if name == "pandoc" else f"/usr/bin/{name}"
        report = run_doctor()

    pandoc = next(item for item in report.checks if item.name == "pandoc")
    assert pandoc.ok is False
    assert "install" in pandoc.fix.lower()
```

- [ ] **Step 2: 实现检查模型**

```python
from pydantic import BaseModel


class DoctorCheck(BaseModel):
    name: str
    ok: bool
    detail: str
    fix: str = ""


class DoctorReport(BaseModel):
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks)
```

- [ ] **Step 3: doctor 至少检查**

```text
python >=3.12,<3.13
pandoc executable
mineru executable（输出 resolve_mineru_command() 解析后的路径与 mineru -v 版本）
tiktoken o200k_base load
corpus_root writable（本机默认 /Volumes/ORICO/LongDocCorpus，需检查外接盘已挂载且可写）
```

修复提示按本机基线（2026-08-29）：

Pandoc 本机已装（3.11 @ /usr/local/bin/pandoc，按 AGENTS.md 禁止 brew 重装）；面向其他机器的通用兜底提示：

```text
brew install pandoc
```

MinerU 本机在 `~/.venvs/mineru/bin/mineru`（不在 PATH，由 resolve_mineru_command() 自动解析）；只有解析也失败时才提示，且不自动安装：

```text
MinerU command not found. Verify the existing MinerU installation with:
ls ~/.venvs/mineru/bin/mineru
~/.venvs/mineru/bin/mineru --version
```

- [ ] **Step 4: 实现 `inspect`**

不生成 Corpus，只输出：

- 输入类型：file/directory；
- 支持文件数；
- 总 bytes；
- 对 `.md/.txt` 估算 tokens；
- PDF/DOCX 显示“需要转换后才能获得准确 token”；
- 将使用的 Adapter；
- 当前 Atomic/Batch profile。

- [ ] **Step 5: 日志**

`logging_utils.py` 实现 JSONL event：

```json
{"timestamp":"2026-08-29T10:00:00+00:00","stage":"preparing","document_id":"D0001","status":"started","message":"Preparing source document"}
```

禁止把全文写进日志。

- [ ] **Step 6: CLI 增加 `doctor` 和 `inspect`**

新手看到失败时，错误输出必须包含：

```text
发生了什么
最可能原因
下一步命令
日志路径
```

不能只打印 Python traceback。

- [ ] **Step 7: 跑测试**

```bash
uv run pytest tests/test_doctor.py -v
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 8: 提交**

```bash
git add src/docchunk/doctor.py src/docchunk/logging_utils.py src/docchunk/cli.py tests/test_doctor.py
git commit -m "feat: add doctor inspect and structured diagnostics"
```

---

## Task 16: 完整 PDF/DOCX/目录集成测试与 Golden Corpus

**目标：** 从“模块都能跑”升级到“真实资料可以放心用”。

**Files:**
- Create/expand: `tests/test_integration_corpus.py`
- Add small legal test fixtures under `tests/fixtures/`
- Do not commit copyrighted books/courses.

**Interfaces:**
- No new public API; validates system invariants.

- [ ] **Step 1: Markdown Golden Test**

固定 fixture，保存期望：

```text
atomic count
atomic char spans
batch new_atomic_ids
batch overlap_atomic_ids
```

升级 splitter 后如果切点变化，测试会提醒。

- [ ] **Step 2: Directory Set 测试**

目录：

```text
1-第一课.md
2-第二课.txt
10-第十课.md
```

验收：

- Document 顺序 1、2、10；
- `document_id` 分别 `D0001/D0002/D0003`；
- Atomic 全局 sequence 连续；
- 每条 Index 保留对应 source file。

- [ ] **Step 3: Pandoc 集成测试**

测试分两层：

1. 默认 pytest 使用 mock，不要求机器安装 Pandoc；
2. 标记 `@pytest.mark.external` 的测试实际执行 Pandoc。

在 `pyproject.toml` 注册：

```toml
[tool.pytest.ini_options]
markers = [
  "external: requires installed external tools such as pandoc or mineru",
]
```

日常：

```bash
uv run pytest -m "not external"
```

本机完整验收：

```bash
uv run pytest -m external -v
```

- [ ] **Step 4: MinerU 集成测试**

同样用 `external` marker。

实际 PDF 只使用自己生成的两页测试 PDF 或明确允许测试的公开样本，避免把付费书籍提交进仓库。

验收：

- MinerU 生成 Markdown；
- page provenance 非空；
- `verify` PASS。

- [ ] **Step 5: 全套回归**

```bash
uv run pytest -m "not external" --cov=docchunk --cov-report=term-missing
uv run ruff check .
uv run mypy src
```

最低要求：

```text
所有非 external 测试通过
覆盖率 >= 80%
Ruff PASS
mypy PASS
```

不要为了达到覆盖率去写没有断言价值的测试。

- [ ] **Step 6: 真实中文长文 smoke test**

选择你自己有权使用的一份：

```text
10万字以上课程逐字稿 .txt/.md
```

运行：

```bash
uv run docchunk inspect "$HOME/Documents/course.txt"
uv run docchunk split "$HOME/Documents/course.txt"
uv run docchunk verify "/Volumes/ORICO/LongDocCorpus/course-example"
uv run docchunk status "/Volumes/ORICO/LongDocCorpus/course-example"
```

手工抽查：

- 前 3 个 Atomic；
- 中间 3 个 Atomic；
- 最后 3 个 Atomic；
- 前两个 Batch 的 overlap；
- 最后一个 Batch；
- normalized 开头/结尾。

- [ ] **Step 7: 提交**

```bash
git add tests pyproject.toml
git commit -m "test: add corpus integration and golden coverage"
```

---

# Phase A Release Gate

到这里先停止，不进入 Skill 集成。

必须全部满足：

```bash
uv run pytest -m "not external"
uv run ruff check .
uv run mypy src
uv run docchunk doctor
```

并用至少：

- 1 个长 Markdown/TXT；
- 1 个 DOCX；
- 1 个文本 PDF；
- 1 个扫描 PDF；
- 1 个多文件课程目录；

实际运行 `split + verify`。

只有这五类都通过，才进入 Phase B。

建议打 tag：

```bash
git tag v0.1.0-cli
git log --oneline --decorate -10
```

---

# Phase B — `longdoc-router` Skill 与下游 Skill 适配

## Task 17: 建立 `longdoc-router` Skill 骨架和 Corpus Contract

**目标：** Skill 只做编排，不复制 docchunk 算法，也不复制第三方蒸馏逻辑。

**Files:**
- Create: `skills/longdoc-router/SKILL.md`
- Create: `skills/longdoc-router/references/corpus-contract.md`
- Create: `skills/longdoc-router/references/routing.md`

**Interfaces:**
- Consumes a `docchunk` Corpus path
- Routes to `cangjie-skill`, `nuwa-skill`, or direct batch reading
- Emits downstream run state

- [ ] **Step 1: 写 `corpus-contract.md`**

必须明确：

```text
权威入口：manifest.json
Atomic 权威索引：index.jsonl
模型阅读入口：batches/Bxxxx.md
source/normalized.md 只用于校验和回查
不得让下游重新切 normalized.md
overlap_atomic_ids 只能作为上下文，不当作新材料
```

- [ ] **Step 2: 写 routing rule**

固定：

```text
书籍 / 课程 / 方法论 / 播客逐字稿 / 视频文字稿
→ cangjie-skill

人物的大量书籍 / 访谈 / 演讲 / 博客，目标为人物心智模型
→ nuwa-skill

用户只要求“分批深读/总结”，没有要求 Skill 蒸馏
→ 不强行调用 Cangjie/Nuwa，按 Batch 顺序处理

蒸馏结果要求进入个人能力库
→ 完成专业蒸馏后，再调用 personal-capability-distiller
```

- [ ] **Step 3: 写 SKILL.md 的硬规则**

必须包括：

```text
1. 对长文档先检查是否已经存在可验证 Corpus。
2. 没有 Corpus 才调用 docchunk。
3. docchunk verify 不通过，禁止开始下游蒸馏。
4. 不修改第三方 Skill。
5. 不自行创造滚动摘要污染 Corpus。
6. 不把 overlap 当新材料。
7. 中断时记录当前 Batch，恢复时从失败 Batch 继续。
```

- [ ] **Step 4: 人工审阅**

检查 Skill 是否出现：

- 自己实现切片算法；
- 自己总结书；
- 写死 Cangjie 仓库内部实现细节；
- 自动把原书复制到 Obsidian。

出现任何一项都删掉。

- [ ] **Step 5: 提交**

```bash
git add skills/longdoc-router
git commit -m "feat: add longdoc router skill contract"
```

---

## Task 18: Cangjie Adapter 文档与分批调度协议

**目标：** 让 Cangjie 在面对 docchunk Corpus 时，不再自己按“5 万字”等临时策略重新切原文。

**Files:**
- Create: `skills/longdoc-router/references/cangjie-adapter.md`
- Create: `skills/longdoc-router/references/resume.md`

**Interfaces:**
- Input: validated Corpus
- Output: Cangjie-produced distilled artifacts
- Does not modify Cangjie repo

- [ ] **Step 1: 写 Cangjie 输入协议**

规则：

```text
1. 读取 manifest.json。
2. 按 Batch ID 升序处理，例如 B0001 → B0002 → B0003。
3. 每个 Batch 先识别 Context Bridge，再只对 New Material 做新的提取。
4. 需要回查原文时，根据 Atomic id 查 index.jsonl。
5. 需要页码时使用 source.page_start/page_end。
6. 不重新对 normalized.md 进行自由分块。
```

- [ ] **Step 2: 保留 Cangjie 自己的方法论**

明确写：

```text
docchunk 只替代“读取大文件时的临时分块方式”，
不替代 Cangjie 的 Adler 整体理解、提取、验证、Skill 构造等流程。
```

- [ ] **Step 3: 写断点文件规范**

每个 downstream run 独立放：

```text
CORPUS/runs/cangjie-20260829-180000/
├── run.json
├── completed-batches.jsonl
└── outputs/
```

`run.json` 至少：

```json
{
  "adapter": "cangjie",
  "status": "running",
  "manifest_sha256": "3f786850e387550fdab836ed7e6dc881de23001b",
  "current_batch": "B0012",
  "completed_batches": ["B0001", "B0002"]
}
```

- [ ] **Step 4: 恢复规则**

```text
manifest hash 未变
→ 从 current/failed Batch 继续

manifest hash 已变
→ 停止恢复，提示建立新 run

Cangjie Skill 版本变了
→ Corpus 不重建；由用户选择继续旧 run 或新建 downstream run
```

- [ ] **Step 5: 提交**

```bash
git add skills/longdoc-router/references/cangjie-adapter.md \
        skills/longdoc-router/references/resume.md
git commit -m "feat: define cangjie batch adapter"
```

---

## Task 19: Nuwa Adapter

**目标：** 人物蒸馏时保留“每一份来源材料”的身份，不把多本书/访谈揉成无法追溯的一坨文本。

**Files:**
- Create: `skills/longdoc-router/references/nuwa-adapter.md`

**Interfaces:**
- Input: Directory Corpus with multiple document identities
- Output: Nuwa artifacts
- Does not modify Nuwa repo

- [ ] **Step 1: 固定来源原则**

写入：

```text
每个文件必须保留 document_id。
Nuwa 在跨来源验证时使用 document_id/source_file。
不得将多个 source 的 normalized text 先合并成无来源字符串。
```

- [ ] **Step 2: 定义多来源顺序**

默认：

```text
Manifest documents order
→ 每个 document 内 Batch order
```

若 Nuwa 自己要求按来源权重排序，由 Nuwa 决定“阅读顺序”，但不得改变 Corpus 物理顺序和 provenance。

- [ ] **Step 3: 来源引用**

Nuwa 产出若需要 evidence：

```text
document_id
atomic_id
source_file
page range（如存在）
```

- [ ] **Step 4: 提交**

```bash
git add skills/longdoc-router/references/nuwa-adapter.md
git commit -m "feat: define nuwa multi-source adapter"
```

---

## Task 20: `personal-capability-distiller` Adapter 与 Obsidian Pointer 契约

**目标：** 把 Cangjie/Nuwa 的蒸馏结果交给个人能力蒸馏，而不是把整本书和全部 Atomic 复制进 Obsidian。

**Files:**
- Create: `skills/longdoc-router/references/personal-capability-adapter.md`

**Interfaces:**
- Input: downstream distilled Markdown / Skills
- Output: handoff package for `personal-capability-distiller`

- [ ] **Step 1: 固定 handoff 内容**

交给个人能力蒸馏层：

```text
distilled artifact path
source title
source type
raw source pointer
raw source SHA256
corpus_id
corpus path
manifest path
downstream adapter used
downstream output path
```

- [ ] **Step 2: 明确禁止**

```text
不自动复制 source/normalized.md 到 Obsidian
不自动复制 atomic/
不自动复制 batches/
不覆盖 01_来源资料中的既有同名来源
```

- [ ] **Step 3: 定义 `01_来源资料` 推荐指针笔记**

示意：

```markdown
---
title: Agent课程
source_sha256: 3f786850e387550fdab836ed7e6dc881de23001b
corpus_id: agent课程-abcd1234
corpus_path: /Volumes/ORICO/LongDocCorpus/agent课程-abcd1234
manifest_path: /Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/manifest.json
distiller: cangjie-skill
---

# 来源

- 原始资料：`~/Documents/Agent课程.md`
- Corpus：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234`
- Manifest：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/manifest.json`
- 蒸馏产物：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/runs/cangjie-20260829-180000/outputs`

本笔记只保存来源指针；完整原始 Corpus 不复制进 Obsidian。
```

- [ ] **Step 4: 适配现有个人能力 Skill 的人机确认点**

由于 `personal-capability-distiller` 自己要求阶段确认，router 不得绕过：

```text
human_material_approved
skill_simulation_passed
用户明示安装
```

- [ ] **Step 5: 提交**

```bash
git add skills/longdoc-router/references/personal-capability-adapter.md
git commit -m "feat: define personal capability handoff"
```

---

## Task 21: Router 场景测试

**目标：** 不需要真正跑几十万字，也要证明 Router 在不同请求下选择正确路径。

**Files:**
- Create: `skills/longdoc-router/references/test-scenarios.md`

- [ ] **Step 1: 写至少 8 个测试场景**

必须覆盖：

### 场景 1：长课程逐字稿 → Cangjie

```text
用户：把这个 30 万字课程逐字稿做成可执行 Skill。
Expected:
docchunk → verify → cangjie → 可选 personal-capability-distiller
```

### 场景 2：人物访谈资料集 → Nuwa

```text
用户：把这个人的 40 篇访谈和两本书蒸馏成人物思维 Skill。
Expected:
directory corpus → verify → nuwa
```

### 场景 3：只分片，不蒸馏

```text
用户：只帮我把 PDF 切成适合 Codex 阅读的小段。
Expected:
docchunk only
```

### 场景 4：已有 Corpus

```text
Expected:
verify existing corpus
不要重复 MinerU/Pandoc
```

### 场景 5：verify 失败

```text
Expected:
停止 downstream
报告损坏
```

### 场景 6：Cangjie 在 B0017 中断

```text
Expected:
保留 B0001-B0016 状态
从 B0017 恢复
```

### 场景 7：只改 Batch 32K

```text
Expected:
rebuild-batches
Atomic 不变
```

### 场景 8：蒸馏后进入个人能力库

```text
Expected:
只传蒸馏产物 + Corpus pointer
不复制原始 Corpus 到 Obsidian
```

- [ ] **Step 2: 用 Codex/Claude Code 人工模拟**

让 Agent 读取 Skill，并对每个场景回答“下一步要执行什么”。

人工检查是否符合 Expected。

- [ ] **Step 3: 提交**

```bash
git add skills/longdoc-router/references/test-scenarios.md
git commit -m "test: add longdoc router scenario matrix"
```

---

# Phase C — 新手文档、安装体验和 V1 发布

## Task 22: 写 README 的“5 分钟上手”和完整命令手册

**目标：** 一个没写过 Python 的人，也知道安装后怎么用。

**Files:**
- Modify: `README.md`

**README 必须按以下顺序：**

1. 这是什么；
2. 为什么不是简单按字符切；
3. 安装；
4. doctor；
5. TXT/MD 示例；
6. DOCX 示例；
7. PDF/MinerU 示例；
8. 整个课程文件夹示例；
9. 输出目录解释；
10. `verify`；
11. `rebuild-batches`；
12. 怎么交给 Codex；
13. 怎么交给 Cangjie/Nuwa；
14. 常见错误；
15. 升级与卸载；
16. 隐私说明。

- [ ] **Step 1: 安装命令写成可复制版本**

开发安装：

```bash
git clone https://github.com/hg199074jin/docchunk.git
cd docchunk
uv sync
uv run docchunk doctor
```

正式发布 PyPI 之前，不写 `pip install docchunk`，避免给用户一个尚不存在的安装方式。

- [ ] **Step 2: 新手第一条测试**

```bash
echo "第一段。第二段。第三段。" > demo.txt
uv run docchunk split demo.txt
```

然后：

```bash
uv run docchunk status "/实际输出的Corpus路径"
uv run docchunk verify "/实际输出的Corpus路径"
```

- [ ] **Step 3: PDF 示例**

README 必须先提示（docchunk 会自动按 PATH → `~/.venvs/mineru/bin/mineru` 解析 MinerU 路径，`docchunk doctor` 可直接查看解析结果）：

```bash
uv run docchunk doctor
```

再运行：

```bash
uv run docchunk split "$HOME/Documents/book.pdf"
```

- [ ] **Step 4: 文件夹示例**

```bash
uv run docchunk split "$HOME/Documents/课程"
```

解释：

```text
1-第一课.md
2-第二课.md
10-第十课.md
```

按自然文件名排序为一个 Document Set。

- [ ] **Step 5: 常见错误表**

至少写：

| 症状 | 原因 | 怎么办 |
|---|---|---|
| `Pandoc executable was not found` | 没装或 PATH 不对 | `brew install pandoc` |
| `MinerU executable was not found` | MinerU 不在 PATH（本机装在 `~/.venvs/mineru/bin/mineru`） | `uv run docchunk doctor`；仍失败则在配置中写可执行文件绝对路径 |
| verify missing atomic | Corpus 被人为移动/删除 | 保留原 Corpus，重新 split 或修复损坏文件 |
| forced split 很多 | OCR 无标点/超大表格 | 检查 MinerU 输出质量 |
| 第二次 split 没重新 OCR | 正常幂等复用 | source hash 未变化 |
| 改 24K 为 32K | 不需要重新切 Atomic | `rebuild-batches` |

- [ ] **Step 6: 提交**

```bash
git add README.md
git commit -m "docs: add beginner installation and usage guide"
```

---

## Task 23: 最终 V1 验收、版本号与发布前检查

**目标：** 不凭“看起来能用”宣布完成，必须拿证据。

**Files:**
- Modify: `src/docchunk/__init__.py`
- Modify: `pyproject.toml`
- No feature changes allowed during this task except fixes required by failing verification.

- [ ] **Step 1: Clean install 验证**

新临时目录：

```bash
cd /tmp
git clone https://github.com/hg199074jin/docchunk.git docchunk-clean
cd docchunk-clean
uv sync
uv run docchunk doctor
```

- [ ] **Step 2: 测试**

```bash
uv run pytest -m "not external" --cov=docchunk --cov-report=term-missing
uv run ruff check .
uv run mypy src
```

Expected:

```text
0 failed
coverage >= 80%
ruff exit 0
mypy exit 0
```

- [ ] **Step 3: 外部工具测试**

在 MinerU、Pandoc 安装正常的 Mac 上：

```bash
uv run pytest -m external -v
```

- [ ] **Step 4: 五类真实输入验收**

分别运行：

```text
A. 10万字以上 TXT/MD
B. DOCX
C. 文本 PDF
D. 扫描 PDF
E. 多文件课程目录
```

每个都必须：

```bash
docchunk split
docchunk verify
docchunk status
```

并保存命令输出到发布检查记录。

- [ ] **Step 5: 人工质量抽查**

每类至少检查：

```text
开头
25%
50%
75%
结尾
```

确认：

- 没明显句中机械截断；
- 标题没有大量孤立；
- Batch overlap 是完整 Atomic；
- PDF 页码基本对应；
- 原文未被总结或去口语。

- [ ] **Step 6: 更改 Batch profile 验收**

对一个已经成功的 Corpus：

```bash
uv run docchunk rebuild-batches CORPUS \
  --target-tokens 32000 \
  --overlap-atomic-count 1
```

再次：

```bash
uv run docchunk verify CORPUS
```

并比较 Atomic hash，必须完全不变。

- [ ] **Step 7: 中断恢复验收**

人为制造 downstream run：

```text
B0001-B0010 completed
B0011 failed
```

让 longdoc-router 恢复。

Expected:

```text
从 B0011 开始
不重新执行 B0001-B0010
不重新 split Corpus
```

- [ ] **Step 8: 路由验收**

分别测试：

```text
书籍 → Cangjie
课程逐字稿 → Cangjie
人物资料集 → Nuwa
只分片 → docchunk only
蒸馏后个人沉淀 → personal-capability-distiller
```

- [ ] **Step 9: 版本号**

确认全部验收后：

`src/docchunk/__init__.py`:

```python
__version__ = "1.0.0"
```

`pyproject.toml`:

```toml
version = "1.0.0"
```

- [ ] **Step 10: 最后一轮验证**

```bash
uv lock
uv sync --locked
uv run pytest -m "not external"
uv run ruff check .
uv run mypy src
git status
```

`git status` 应干净，除非明确有尚未提交的发布文档。

- [ ] **Step 11: 提交和 tag**

```bash
git add .
git commit -m "release: docchunk v1.0.0"
git tag -a v1.0.0 -m "docchunk v1.0.0"
```

---

# 2. 实施过程中绝对不要做的事情

以下任何一个行为都会让项目偏离设计：

1. 为了“更智能”让 LLM 决定 Atomic 切点。
2. Atomic 自己做 overlap。
3. 一开始就把 Batch 设置到 128K/256K。
4. 把 `semantic-text-splitter`、LangChain、LlamaIndex、Chonkie 全部一起塞进项目。
5. PDF 只读取 MinerU `.md`，完全丢掉 page provenance。
6. DOCX Pandoc 失败后静默改用其他解析器。
7. 删除逐字稿的口语、重复或“废话”。
8. 在 docchunk 内部生成总结。
9. 把所有函数写进一个 2000 行的 `cli.py`。
10. 每次重新运行都重新 OCR 整个 PDF。
11. 改 Batch 大小时重新切 Atomic。
12. Router 修改 Cangjie/Nuwa 源码。
13. Router 自动越过 `personal-capability-distiller` 的人工确认点。
14. 把完整 Atomic/Batch 默认复制进 Obsidian。
15. 测试失败时通过删测试、skip 或弱化断言绕过去。

---

# 3. 推荐的 Git 提交顺序

最终 `git log --oneline` 大致应像：

```text
release: docchunk v1.0.0
docs: add beginner installation and usage guide
test: add longdoc router scenario matrix
feat: define personal capability handoff
feat: define nuwa multi-source adapter
feat: define cangjie batch adapter
feat: add longdoc router skill contract
test: add corpus integration and golden coverage
feat: add doctor inspect and structured diagnostics
feat: add idempotence resume and batch rebuilding
feat: verify corpus integrity
feat: wire document splitting pipeline
feat: build reading batches with atomic overlap
feat: persist corpus atomic files and indexes
feat: preserve markdown structures during splitting
feat: add lossless natural-boundary atomic splitter
feat: add input discovery and adapter routing
feat: add mineru pdf adapter with provenance
feat: add pandoc docx adapter
feat: add markdown and text adapters
feat: add config fingerprints and tokenizer
feat: define corpus data contracts
chore: bootstrap docchunk project
```

如果 Git 历史完全不同并不代表失败，但不要把所有开发压成一个巨大的 commit。

---

# 4. 给 Agent 的分阶段执行模板

## Phase A 开始时

```text
你现在负责实现 docchunk CLI 的 Phase A。

先完整阅读：
- docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md
- docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md

硬性规则：
1. 一次只执行当前 Task。
2. 严格 TDD。
3. 不提前实现后续功能。
4. 每个 Task 结束后运行该 Task 指定的 pytest、Ruff、mypy。
5. 测试通过后单独 commit。
6. 不修改已批准的架构。
7. 遇到 MinerU CLI 与文档示例不一致时，以本机 `mineru --help` 为准，只调整 Adapter 命令层，不改变公开数据契约。

现在执行 Task 1。
```

之后：

```text
继续执行 Task 2。先重新读取 Task 2 的 Files、Interfaces 和步骤；不要提前执行 Task 3。
```

依次推进。

## Phase B 开始前

先给 Agent：

```text
在开始 Phase B 前，先证明 Phase A Release Gate 已通过。

请运行：
uv run pytest -m "not external"
uv run ruff check .
uv run mypy src
uv run docchunk doctor

并汇报五类真实输入 smoke test 状态：
TXT/MD、DOCX、文本 PDF、扫描 PDF、目录。

只有这些通过后，才开始 Task 17。
```

---

# 5. 最终用户日常体验应该是什么样

V1 完成以后，你不需要记复杂 Python 命令。

## 场景 A：一份超长课程逐字稿

```bash
docchunk split "/Users/you/Courses/课程逐字稿.md"
```

返回：

```text
/Volumes/ORICO/LongDocCorpus/课程逐字稿-xxxxxxxxxxxx
```

然后：

```bash
docchunk verify "/Volumes/ORICO/LongDocCorpus/课程逐字稿-xxxxxxxxxxxx"
```

Expected:

```text
PASS
```

你对 Codex 说：

```text
请用 longdoc-router 处理这个 Corpus：
/Volumes/ORICO/LongDocCorpus/课程逐字稿-xxxxxxxxxxxx

这是课程逐字稿，目标是调用 cangjie-skill 蒸馏。
完成专业蒸馏后，再交给 personal-capability-distiller 做个人能力沉淀。
```

## 场景 B：一本扫描 PDF

```bash
docchunk doctor
docchunk split "/Users/you/Books/book.pdf"
```

内部：

```text
PDF
→ MinerU/OCR
→ normalized Markdown + content_list provenance
→ Atomic
→ Batch
→ verify
```

你不需要手工把 PDF 转成十几个文件。

## 场景 C：一整套课程

目录：

```text
课程/
├── 01-导论.md
├── 02-Agent基础.md
├── 03-Memory.md
├── 04-工具调用.md
└── 05-实战.md
```

执行：

```bash
docchunk split "/Users/you/Courses/课程"
```

它会把目录视为一个 Document Set，但每个文件仍保留独立来源身份。

## 场景 D：以后模型更强，想从 24K 改 32K

不重新 OCR、不重新转换、不重新切原文：

```bash
docchunk rebuild-batches "/Volumes/ORICO/LongDocCorpus/course-example" \
  --target-tokens 32000 \
  --overlap-atomic-count 1
```

然后：

```bash
docchunk verify "/Volumes/ORICO/LongDocCorpus/course-example"
```

Atomic 保持不变。

---

# 6. 完成定义（Definition of Done）

只有同时满足以下条件，才能说 V1 “做完了”：

## CLI

- [ ] `docchunk doctor` 可用；
- [ ] `docchunk inspect` 可用；
- [ ] `docchunk prepare` 可用；
- [ ] `docchunk split` 可用；
- [ ] `docchunk batch` 可用；
- [ ] `docchunk verify` 可用；
- [ ] `docchunk status` 可用；
- [ ] `docchunk rebuild-batches` 可用。

## 输入

- [ ] TXT；
- [ ] Markdown；
- [ ] DOCX/Pandoc；
- [ ] PDF/MinerU；
- [ ] 扫描 PDF/OCR；
- [ ] Directory Document Set。

## 输出契约

- [ ] 每个 Atomic 都有独立 `.md` 文件和序号；
- [ ] `index.jsonl` 每行都带来源位置；
- [ ] `combined.md` 可作为单文件阅读视图；
- [ ] `combined.md` 被明确标记为派生视图，不参与无损重建权威判断。

## 数据质量

- [ ] Atomic 无意外缺口；
- [ ] Atomic 无意外重复；
- [ ] Atomic 无 overlap；
- [ ] Batch overlap 为完整 Atomic；
- [ ] source/normalized 可重建；
- [ ] PDF provenance 能追到页码；
- [ ] forced split 有显式 flag；
- [ ] fallback 有显式 flag；
- [ ] verify 可检测人为损坏。

## 稳定性

- [ ] 相同输入可复用；
- [ ] 改 Batch 不重切 Atomic；
- [ ] downstream 中断可 resume；
- [ ] 外部工具失败有清晰恢复命令；
- [ ] 原始文件从不覆盖。

## Skill

- [ ] 课程/书籍能路由 Cangjie；
- [ ] 人物资料集能路由 Nuwa；
- [ ] 只分片时不强制蒸馏；
- [ ] 完成后可交给 personal-capability-distiller；
- [ ] 三个第三方 Skill 均未被 fork/修改；
- [ ] Corpus 没有默认复制进 Obsidian。

## 工程质量

- [ ] 非 external pytest 全通过；
- [ ] external smoke test 在本机通过；
- [ ] Ruff 通过；
- [ ] mypy 通过；
- [ ] 测试覆盖率 ≥80%；
- [ ] README 可让新用户完成第一次 split；
- [ ] Git 历史按任务可回滚；
- [ ] `v1.0.0` tag 创建。

---

# 7. 实施顺序总览

不要打乱：

```text
Task 1   项目骨架
Task 2   数据契约
Task 3   配置 / Hash / Tokenizer
Task 4   MD/TXT Adapter
Task 5   Pandoc DOCX
Task 6   MinerU PDF + Provenance
Task 7   文件/目录发现
Task 8   Atomic 自然语言切片
Task 9   Markdown 结构保护
Task 10  Corpus 持久化
Task 11  Reading Batch
Task 12  Pipeline + split CLI
Task 13  verify
Task 14  幂等 / resume / rebuild
Task 15  doctor / inspect / 日志
Task 16  集成测试
          ↓
      Phase A Gate
          ↓
Task 17  longdoc-router
Task 18  Cangjie Adapter
Task 19  Nuwa Adapter
Task 20  personal-capability Adapter
Task 21  Router 场景测试
Task 22  新手 README
Task 23  V1 最终验收和发布
```

先把“可靠阅读长文档”做稳，再接“怎么蒸馏”，最后才接“怎么沉淀成自己的能力”。

这也是整个项目最重要的工程原则。
