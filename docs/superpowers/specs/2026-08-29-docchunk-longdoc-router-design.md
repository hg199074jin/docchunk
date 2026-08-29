# docchunk + longdoc-router V1 设计文档

> 状态：Design Approved for Review（设计稿，尚未进入实施）  
> 目标版本：V1.0  
> 设计目标：让超长书籍、课程逐字稿、PDF、Word、Markdown 等资料能够被大模型**高质量、连续、可恢复、可追溯地阅读**，而不是仅仅“塞进上下文”。

---

## 1. 背景与问题定义

大模型上下文窗口持续增大，但“能够容纳”不等于“能够高质量理解”。当一次向模型提供几十万 token 的书籍或课程逐字稿时，常见问题包括：

- 模型只抓主线，遗漏细节、例外、案例与论证过程；
- 前后信息竞争，早期内容在后续推理中权重下降；
- 长逐字稿中存在大量口语、重复、例子与跨段呼应，简单按字符切割容易破坏语义；
- 不同模型上下文窗口不同，若切片直接绑定某个模型，未来更换模型就要重新处理原文；
- 长任务中途失败后，如果没有 checkpoint/resume，会造成重复消耗；
- 如果没有来源定位，后续蒸馏结果无法可靠回查到原书页码、原章节或原文本位置；
- 现有蒸馏 Skill 通常擅长“理解和提炼”，但并不负责严谨的长文档预处理、完整性验证和可重复的 batch 编排。

因此，本项目不做新的“总结器”或“蒸馏器”，而是建设一个位于上游的**长文档阅读基础设施**。

核心原则：

> **Chunking is lossless. Distillation may be lossy.**  
> 切片必须尽可能无损；真正的认知压缩、总结、提炼、重构交给下游成熟 Skill。

---

## 2. 项目定位

项目由两个相互独立但协同工作的组件组成：

### 2.1 `docchunk` CLI

职责：确定性、可验证、模型无关的长文档预处理。

负责：

- 文件识别；
- PDF / Word / Markdown / TXT 预处理；
- MinerU / Pandoc 调用；
- 统一标准化；
- token 计数；
- 自然语言边界切片；
- Atomic Chunk 生成；
- Reading Batch 编排；
- Batch overlap；
- 来源位置追踪；
- JSONL / Markdown / Manifest 输出；
- 完整性验证；
- SHA256；
- 幂等处理；
- checkpoint / resume 所需状态数据。

明确不负责：

- 不调用 LLM 判断内容重要性；
- 不总结；
- 不改写；
- 不删除“口语废话”；
- 不判断作者观点是否正确；
- 不创建最终 Skill；
- 不写入 Obsidian 能力库。

### 2.2 `longdoc-router` Skill

职责：Agent 工作流编排与下游 Skill 路由。

负责：

- 识别用户提交的是普通短资料还是需要长文档处理；
- 必要时调用 `docchunk`；
- 按 Manifest 顺序读取 Reading Batches；
- 管理断点状态；
- 根据用户目标选择下游 Skill；
- 将标准 Corpus 适配给 Cangjie、Nuwa 或未来其他蒸馏 Skill；
- 在蒸馏完成后，根据用户需求继续交给 `personal-capability-distiller`。

不负责重新实现 Cangjie、Nuwa 或个人能力蒸馏逻辑。

---

## 3. 已确认的产品边界

### 3.1 V1 输入

支持：

- `.pdf`
- `.docx`
- `.md`
- `.markdown`
- `.txt`
- 一个包含上述文件的目录

目录可表示：

- 一整门课程；
- 一本书分卷；
- 多章节逐字稿；
- 一组访谈材料；
- 一个资料集。

V1 不要求直接支持：

- PPTX；
- Excel；
- 音视频下载与 ASR；
- EPUB/MOBI；
- 网页抓取。

这些可以后续作为 Adapter 扩展，但不进入 V1 核心范围。

### 3.2 V1 下游

默认路由：

- 书籍 / 课程 / 长视频逐字稿 / 播客文字稿 / 方法论资料 → `cangjie-skill`
- 人物认知 / 思维框架 / 表达 DNA / 决策逻辑 → `nuwa-skill`
- 蒸馏结果需要进入个人长期能力体系 → `personal-capability-distiller`

原则：

> 第三方 Skill 不修改、不 fork、不复制核心逻辑。  
> `longdoc-router` 只做上游 wrapper/router 和输入适配。

---

## 4. 总体架构

```text
                              User / Codex
                                   │
                                   ▼
                         longdoc-router Skill
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              短文档，可直接读                长文档/资料集
                    │                             │
                    │                             ▼
                    │                         docchunk CLI
                    │                             │
                    │        ┌────────────────────┼────────────────────┐
                    │        │                    │                    │
                    │      PDF                  DOCX                MD/TXT
                    │        │                    │                    │
                    │     MinerU               Pandoc              Direct
                    │        │                    │                    │
                    │        └────────────────────┼────────────────────┘
                    │                             ▼
                    │                    Normalized Document
                    │                             │
                    │                             ▼
                    │                       Atomic Chunks
                    │                             │
                    │                             ▼
                    │                       Reading Batches
                    │                             │
                    │                    manifest + index.jsonl
                    │                             │
                    └─────────────────────────────┤
                                                  ▼
                                      Downstream Skill Router
                                        ┌─────────┴─────────┐
                                        ▼                   ▼
                                  cangjie-skill          nuwa-skill
                                        │                   │
                                        └─────────┬─────────┘
                                                  ▼
                                 personal-capability-distiller
                                                  │
                                                  ▼
                                         Obsidian / 能力树
```

---

## 5. 核心设计：两级切片模型

V1 不采用“直接把全文切成若干 24K 文件”的单层设计，而采用两层结构：

1. **Atomic Chunk：稳定、无重叠、可长期复用的最小阅读单元**；
2. **Reading Batch：根据模型阅读预算临时组合出来的阅读窗口**。

这是整个系统最重要的架构决策之一。

### 5.1 Atomic Chunk

默认目标：

- target：约 6K tokens；
- soft range：约 4K–8K tokens；
- overlap：0；
- hard limit：必须可配置。

Atomic Chunk 的目标不是让模型直接“一片一片总结”，而是形成稳定的数据层。

它应尽可能满足：

- 不截断 Markdown 标题结构；
- 不在完整段落中间切断；
- 超长段落时优先按完整句子切；
- 再不足时按子句、标点边界切；
- 最后才执行 token hard-cut；
- 原文顺序严格保持；
- 每个 Atomic Chunk 有唯一、稳定的 source span。

Atomic Chunk 一旦生成，只要：

- 原始文件未改变；
- 标准化配置未改变；
- tokenizer profile 未改变到需要重新切 Atomic；

就不应重复生成。

### 5.2 Reading Batch

默认目标：

- target：约 24K tokens；
- soft range：约 16K–32K tokens；
- hard context limit profile：默认 256K，可覆盖；
- overlap：默认 1 个完整 Atomic Chunk；
- 不允许从 Atomic Chunk 中间制造 overlap。

Reading Batch 是模型实际阅读的单位。

示例：

```text
Atomic: A001 A002 A003 A004 A005 A006 A007 A008 A009 ...

Batch 001: A001 A002 A003 A004
Batch 002:                A004 A005 A006 A007
Batch 003:                               A007 A008 A009 ...
```

其中 A004、A007 是上下文桥梁。

优点：

- overlap 不污染原始 Atomic 数据；
- 可以明确标识“重复上下文”；
- 更换模型后只需重新编排 Reading Batch，不一定需要重新切 Atomic；
- 可避免机械复制 2K token 时截断半句话。

---

## 6. 自然语言切分策略

### 6.1 边界优先级

切片遵循“最高语义边界优先、逐级降级”原则。

推荐优先级：

1. 文档/文件边界；
2. Markdown 一级标题；
3. Markdown 二级/三级标题；
4. 其他结构化 block；
5. 完整段落；
6. Unicode sentence boundary；
7. 中文强句界：`。！？`；
8. 中文较强子句：`；`；
9. 弱子句：`：，、`；
10. Unicode word/grapheme boundary；
11. 最后兜底 token hard-cut。

### 6.2 核心库选择

V1 推荐：

- 主切分核心：`semantic-text-splitter`（`benbrandt/text-splitter` 的 Python binding）；
- tokenizer：`tiktoken`，OpenAI profile 默认 `o200k_base`；
- `semchunk`：不作为 V1 必需 runtime dependency，保留为基准测试/可替换 backend。

选择 `semantic-text-splitter` 的原因：

- 原生支持 token sizing；
- 支持容量范围，而不是只能固定长度；
- Markdown 模式按 CommonMark 层级处理；
- 使用 Unicode sentence/word/grapheme boundary；
- 算法思想与本项目“尽量保持最大语义单元”一致；
- 依赖相对轻。

`semchunk` 的 offsets 和 overlap 能力非常有价值，但 V1 的来源映射和 overlap 均由项目自身数据模型控制，因此先作为测试对照和未来可插拔 backend，而不同时引入两套核心实现。

### 6.3 中文补强

不能完全依赖英文标点逻辑。V1 应在 splitter 前后增加中文边界 policy：

- `。！？` 视为强边界；
- `；` 为次强边界；
- `：`、`，`、`、` 仅在前述边界无法满足 token hard limit 时使用；
- 连续标点、引号、括号需要作为一个边界组处理，避免出现 `。“` 或 `）` 被分离；
- 对 OCR 后异常无标点长段，应允许最终降级到 tokenizer hard-cut，并在 metadata 中标记 `forced_split=true`。

---

## 7. 表格、代码块、引用等特殊结构

### 7.1 Markdown 表格

默认策略：

- 表格整体能放入 Atomic Chunk → 不拆；
- 单表超过 Atomic soft max、但未超过 hard limit → 允许 Atomic 超出 target；
- 单表超过 hard limit → 按行拆分，并在每个子表重复表头；
- metadata 标记：
  - `structure_type=table`
  - `split_table=true`
  - `table_part=x/y`

不能为了“表格绝不拆”而突破 hard context limit。

### 7.2 代码块

V1 主要服务书籍/逐字稿，不以代码文档为主，但仍需要：

- 尽量保持 fenced code block 完整；
- 超过 hard limit 才拆；
- 拆分时不得破坏 Unicode；
- metadata 标记 forced split。

### 7.3 引用、列表、脚注

- block quote 尽可能作为整体；
- Markdown list 优先按 list item 边界拆；
- 脚注尽量和对应正文保持在同一结构区域，但不以牺牲 hard limit 为代价。

---

## 8. 输入 Adapter 设计

所有输入最终必须转换为统一的 `NormalizedDocument` 数据模型。

### 8.1 PDF Adapter：MinerU First

PDF 默认使用已安装的 MinerU。

本机环境事实（2026-08-29 核实）：

- MinerU 3.4.5 安装在 `~/.venvs/mineru/bin/mineru`，**不在系统 PATH**；docchunk 在代码层解析可执行路径（PATH 查找 → 回退 `~/.venvs/mineru/bin/mineru`），不修改 shell profile，不修改 `~/mineru.json`，不向该 venv 安装包。
- CLI 契约已核对：`mineru -p <input> -o <output>`（均必填）；docchunk 显式追加 `-b hybrid-engine --effort medium`（可配置），不依赖工具默认值，保证行为确定。
- hybrid-engine + medium 是本机 AGENTS.md 约定的组合；Apple M4 / 24GB 内存运行余量充足（medium 档自动关闭图像/图表分析，更快更省内存）。
- content list 兼容 v1/v2 命名：发现模式用 `*_content_list*.json`，以真实输出为准。

关键要求：不要只消费 MinerU 输出的 `.md`。

同时读取：

- `*.md`
- `*_content_list.json`
- 在需要时读取 `*_middle.json`
- 对 MinerU 新版本，可适配 `*_content_list_v2.json`

原因：MinerU 的 `content_list.json` 为可读内容块保存阅读顺序，并提供 `page_idx` 和 `bbox`；标题还可通过 `text_level` 恢复层级。因此 PDF 可以建立：

```text
Chunk → Normalized Span → MinerU Block → PDF Page/BBox
```

来源追踪至少包含：

- 原 PDF 文件；
- 页码起止；
- MinerU block id / 顺序；
- heading path；
- normalized char range；
- 必要时 bbox。

### 8.2 DOCX Adapter：Pandoc First

默认：DOCX → Pandoc → Markdown。

原因：Pandoc 对 Word/Markdown 的结构转换成熟、CLI 稳定，并能较好保留标题、列表、普通表格等结构。

注意：Pandoc 官方也明确指出从表达能力更强的格式转换到 Markdown 可能存在信息损失，尤其复杂表格与格式细节。因此：

- 原 DOCX 永久保留 checksum 和 source pointer；
- normalized Markdown 是阅读视图，不宣称与 Word 视觉格式完全等价；
- Pandoc 失败或输出异常时允许 fallback 到 MinerU；
- fallback 必须记录 `adapter_fallback`，不能静默切换。

### 8.3 Markdown Adapter

直接读取，但执行轻量标准化：

- UTF-8；
- 行尾统一；
- 保留标题；
- 保留表格、代码块、链接、引用；
- 不进行内容级改写。

### 8.4 TXT Adapter

纯文本读取后：

- UTF-8 归一；
- 保留原段落；
- 不自动“AI 生成标题”；
- 只通过规则识别空行、段落、自然句界。

### 8.5 Directory / Document Set Adapter

目录作为一个逻辑资料集输入。

V1 默认排序规则：

1. 显式 manifest（未来可选）；
2. 文件名自然排序；
3. 稳定的绝对/相对路径排序兜底。

目录处理必须保留“文件边界”。

禁止将多个文件先粗暴 concatenate 成一个无来源长字符串。

---

## 9. 标准化与“无损”的定义

“无损”在这里不是字节级等价，而是**阅读内容可审计地保真**。

需要区分：

### 9.1 Raw Source

用户原始文件。

只计算 hash，不修改。

### 9.2 Normalized Source

为了 LLM 阅读进行结构化转换后的标准文本。

允许的标准化包括：

- 编码统一；
- 行尾统一；
- DOCX/PDF 转 Markdown；
- MinerU/Pandoc 必要的格式转换；
- 确定性地生成结构标记。

禁止：

- 删除口语；
- 去重段落；
- AI 改写；
- AI 总结；
- 擅自删除免责声明、案例、脚注或看似“不重要”的内容。

### 9.3 可验证保真

`verify` 应验证：

- Atomic chunks 按 source span 重新拼接后，与 normalized source 在定义的规范化规则下等价；
- Atomic 之间无意外缺口；
- Atomic 之间无意外重复；
- 每个 chunk 的 token 数重新计算一致；
- source offsets 单调递增；
- PDF 页码映射合法；
- Batch 引用的 Atomic id 均存在；
- Batch overlap 符合策略；
- manifest 中 hash 与当前文件一致。

---

## 10. Corpus 目录设计

默认 corpus root 可配置，不应硬编码到 Obsidian。

单文档示例：

```text
LongDocCorpus/
└── <corpus-id>/
    ├── manifest.json
    ├── index.jsonl
    ├── state.json
    │
    ├── source/
    │   ├── source-ref.json
    │   ├── normalized.md
    │   └── mineru/              # PDF 时可存在
    │
    ├── atomic/
    │   ├── A000001.md
    │   ├── A000002.md
    │   └── ...
    │
    ├── batches/
    │   ├── B0001.md
    │   ├── B0002.md
    │   └── ...
    │
    └── logs/
        └── processing.jsonl
```

目录资料集：

```text
LongDocCorpus/
└── <course-id>/
    ├── manifest.json
    ├── documents/
    │   ├── D0001/
    │   ├── D0002/
    │   └── ...
    ├── atomic/
    ├── batches/
    ├── index.jsonl
    └── state.json
```

其中全局 Atomic id 跨文档连续，document id 单独保存。

---

## 11. Manifest 数据契约

`manifest.json` 是整个 Corpus 的权威入口。

V1 至少包含：

```json
{
  "schema_version": "1.0",
  "corpus_id": "...",
  "title": "...",
  "created_at": "...",
  "updated_at": "...",
  "source_type": "file|directory",
  "documents": [],
  "normalization": {},
  "tokenizer": {
    "provider": "tiktoken",
    "encoding": "o200k_base"
  },
  "atomic_policy": {
    "target_tokens": 6000,
    "soft_min_tokens": 4000,
    "soft_max_tokens": 8000
  },
  "batch_policy": {
    "target_tokens": 24000,
    "soft_min_tokens": 16000,
    "soft_max_tokens": 32000,
    "overlap_atomic_count": 1
  },
  "counts": {
    "documents": 0,
    "atomic_chunks": 0,
    "reading_batches": 0,
    "normalized_tokens": 0
  },
  "verification": {
    "status": "pending|passed|failed"
  }
}
```

注意：上面是数据契约示意，不是最终 JSON Schema 实现。

---

## 12. `index.jsonl` 数据契约

每行代表一个 Atomic Chunk，方便流式处理。

建议字段：

```json
{
  "atomic_id": "A000123",
  "document_id": "D0003",
  "sequence": 123,
  "path": "atomic/A000123.md",
  "token_count": 5981,
  "char_start": 183920,
  "char_end": 195334,
  "heading_path": ["第三章", "3.2 长上下文"],
  "source": {
    "file": "course-03.pdf",
    "page_start": 42,
    "page_end": 46
  },
  "flags": {
    "forced_split": false,
    "split_table": false
  }
}
```

对于 TXT/MD/DOCX 无 PDF 页码时，页码字段为空，但必须保留：

- source file；
- normalized char offset；
- document-relative order；
- heading path（如果存在）。

---

## 13. Atomic Markdown 文件契约

每个 Atomic 文件包含少量 YAML frontmatter + 原文正文。

示意：

```markdown
---
atomic_id: A000123
document_id: D0003
sequence: 123
tokens: 5981
source_file: course-03.pdf
page_start: 42
page_end: 46
heading_path:
  - 第三章
  - 3.2 长上下文
---

<normalized source text>
```

YAML 只保存高频的人机可读字段；完整字段以 `index.jsonl` 为准。

---

## 14. Reading Batch 文件契约

Batch 是给 Agent 实际阅读的文件，应明确区分“新内容”和“前序重叠”。

示意：

```markdown
---
batch_id: B0012
atomic_ids:
  - A000067
  - A000068
  - A000069
  - A000070
overlap_from_previous:
  - A000067
new_atomic_ids:
  - A000068
  - A000069
  - A000070
tokens: 23891
---

# Context Bridge

> A000067 为上一批已读取内容，仅用于维持上下文连续性。

[Atomic A000067]
...

# New Material

[Atomic A000068]
...
```

这样下游蒸馏 Skill 可以避免把 overlap 当成新知识重复提取。

---

## 15. CLI 设计

CLI 名称：`docchunk`

### 15.1 核心命令

```text
docchunk doctor
docchunk inspect <input>
docchunk prepare <input>
docchunk split <input>
docchunk batch <corpus>
docchunk verify <corpus>
docchunk status <corpus>
docchunk rebuild-batches <corpus>
```

### 15.2 `doctor`

检查：

- Python/runtime；
- Pandoc 是否可执行；
- MinerU 是否可执行（显示解析后的可执行路径与版本，而不是只报"找到/没找到"）；
- tiktoken；
- corpus root 是否可写；
- 可选 backend 状态。

不进行任何文件处理。

修复提示与本机基线一致：Pandoc 3.11 已装于 `/usr/local/bin/pandoc`（官方 pkg，按 AGENTS.md 约定禁止 brew 重装）；MinerU 3.4.5 位于 `~/.venvs/mineru/bin/mineru`（不在 PATH，由配置解析自动回退），仅当解析也失败时才提示检查安装。

### 15.3 `inspect`

只读分析输入：

- 文件类型；
- 文件数量；
- 大小；
- 估算 token；
- 是否需要 MinerU/Pandoc；
- 推荐 profile；
- 预计 Atomic/Batch 数量。

不生成 Corpus。

### 15.4 `prepare`

只负责 Adapter + normalize，不切片。

适合调试 MinerU/Pandoc 输出。

### 15.5 `split`

执行：

```text
prepare → atomic split → index → default batch → verify
```

这是日常主入口。

### 15.6 `batch`

在现有 Atomic 上根据指定 profile 生成一套 Batch。

未来可允许多个 batch profile 并存，例如：

```text
batches/codex-24k/
batches/claude-32k/
```

V1 数据结构应预留能力，但 UI 可以只实现一个 active profile。

### 15.7 `rebuild-batches`

只重建 Batch，不重新调用 MinerU/Pandoc，不重新切 Atomic。

这是两级架构的重要收益。

### 15.8 `verify`

执行完整性与一致性检查。

### 15.9 `status`

输出 Corpus 当前状态：

- source hash；
- normalized；
- atomic；
- batch；
- verify；
- downstream processing state。

---

## 16. 配置与 Profile

配置优先级：

```text
CLI 参数 > 项目配置 > 用户全局配置 > 内置默认值
```

建议配置项：

- corpus root（本机默认 `/Volumes/ORICO/LongDocCorpus`，与 MinerU 模型同盘；始终可用 `--corpus-root` 覆盖）；
- MinerU executable（支持绝对路径；未显式配置时 PATH 查找并回退 `~/.venvs/mineru/bin/mineru`）；
- MinerU backend（默认 `hybrid-engine`）与 effort（默认 `medium`）；
- Pandoc executable；
- tokenizer；
- Atomic target/min/max；
- Batch target/min/max；
- overlap atomic count；
- hard context limit；
- supported extensions；
- output language metadata；
- logs level。

### 16.1 Codex 默认 Profile

当前项目约定的默认阅读策略：

```text
hard_context_limit: 256K
atomic_target:        6K
atomic_soft_range:    4K–8K
batch_target:        24K
batch_soft_range:    16K–32K
batch_overlap:        1 Atomic Chunk
```

256K 是安全 hard profile，不代表默认会把 256K 原文塞给模型。

---

## 17. `longdoc-router` Skill 设计

### 17.1 触发场景

典型触发：

- “把这本书蒸馏成 Skill”；
- “把这个很长的课程逐字稿交给仓颉”；
- “这个 PDF 太长了，分批深读”；
- “把这个目录的全部课程一起处理”；
- “用 Nuwa 蒸馏这个人的全部访谈和书”。

### 17.2 Router 的工作步骤

```text
1. 识别任务目标
2. inspect 输入
3. 若输入超过直接阅读阈值 → 调 docchunk split
4. verify 必须通过
5. 加载 manifest
6. 决定 downstream adapter
7. 按 Batch 顺序提供材料
8. 维护 downstream checkpoint
9. 下游 Skill 完成
10. 若用户需要长期沉淀 → personal-capability-distiller
```

### 17.3 不做“前文摘要”

Router 不应自行创建滚动摘要作为 Corpus 一部分。

原因：

- 摘要已经是有损认知加工；
- 会把 Router 的理解偏差传递给下游专业 Skill；
- Cangjie/Nuwa 本身有自己的整体理解和方法论。

Router 只提供：

- overlap Atomic；
- manifest；
- source metadata；
- Batch 顺序；
- 已处理状态。

---

## 18. Cangjie Adapter

Cangjie 的定位是将书籍、长视频、播客等高价值内容中的方法论和框架转成可调用 Skill，并已有整体内容理解、并行提取、验证和 Skill 构造流程。

本项目不改 Cangjie。

Adapter 只提供约定：

- 如果输入存在 docchunk Manifest，则优先使用标准 Corpus；
- 不再让 Agent 对原始 30 万字文本自行临时分块；
- 每个 extractor 可按照相同 Batch 顺序完整扫描 Corpus；
- overlap block 明确标为 context-only；
- Cangjie 的原有 Phase 0/Phase 1/验证逻辑保持不变；
- Cangjie 需要引用来源时，从 Atomic metadata 获取章节/页码/文件位置。

目标：

> 改善 Cangjie 的“输入读取基础设施”，而不是改变 Cangjie 的蒸馏方法论。

---

## 19. Nuwa Adapter

Nuwa 负责从人物的大量一手材料中提取心智模型、决策启发式和表达特征。

Adapter 行为：

- 多本书、多篇访谈、多份逐字稿可作为 Directory Corpus；
- 每份 source 保留 document identity；
- 不把多个来源拼成无法区分出处的长字符串；
- Nuwa 仍负责人物建模与交叉验证；
- docchunk 只确保每个来源都可以被稳定、分批、可追溯地读取。

---

## 20. Personal Capability Distiller Adapter

`personal-capability-distiller` 是长期知识与能力沉淀层，不是原始书籍的第一遍长文档读取器。

它当前已经只接受 Markdown/纯文本，并规定 PDF/Word 等先经过转换；内部还负责：

- 资料清点；
- 保真还原；
- 来源观点 / AI 重构 / 个人应用区分；
- 逻辑版 / 使用版 / 定稿版；
- 能力卡；
- 候选 Skill；
- 模拟测试；
- Obsidian 归档；
- 能力树更新。

因此最终链路：

```text
Raw Long Document
      ↓
docchunk Corpus
      ↓
Cangjie / Nuwa
      ↓
Distilled Markdown / Skills
      ↓
personal-capability-distiller
      ↓
Personal Capability Assets
```

### 20.1 Corpus 与 Obsidian 分离

已确认采用 A 方案：

- Corpus 保留完整 normalized source、Atomic、Batch、Manifest；
- Obsidian 不复制全量几十万字原文；
- Obsidian `01_来源资料` 保存：
  - source title；
  - source path/pointer；
  - SHA256；
  - corpus_id；
  - corpus path；
  - manifest pointer；
  - 下游蒸馏结果链接；
  - provenance 信息。

这样 Corpus 是“资料仓库”，Obsidian 是“知识与能力仓库”。

---

## 21. 状态机、断点续跑与幂等

### 21.1 Corpus 处理状态

建议状态：

```text
new
→ preparing
→ prepared
→ splitting
→ split
→ batching
→ batched
→ verifying
→ ready

任意阶段可进入 failed
```

### 21.2 Downstream 阅读状态

每个 downstream run 单独记录：

```text
pending
→ running
→ paused
→ completed
→ failed
```

并记录：

- adapter；
- Skill name/version（如可获取）；
- profile；
- 当前 batch；
- 已完成 batch；
- failed batch；
- output path；
- input manifest hash。

### 21.3 Resume 原则

例如 80 个 Batch 在 B0037 失败：

- B0001–B0036 保留；
- B0037 标记 failed；
- 下一次默认从 B0037 继续；
- 不重新调用 MinerU；
- 不重新生成 Atomic；
- 不重新运行已完成下游步骤，除非用户明确要求。

### 21.4 Hash 与失效规则

至少记录：

- raw source SHA256；
- normalized source SHA256；
- Atomic policy fingerprint；
- tokenizer fingerprint；
- Batch policy fingerprint。

失效策略：

- 原文件 hash 变了 → normalized/Atomic/Batch 全部需要重新评估；
- 仅 Batch target 改了 → 只重建 Batch；
- 仅 downstream Skill 改了 → Corpus 不动，只重跑 downstream；
- 只修改输出位置 → 不重新切片。

---

## 22. 错误处理

### 22.1 MinerU 失败

必须：

- 保留 stderr/log；
- 不生成伪成功 manifest；
- 标记 adapter failure；
- 提供可恢复命令；
- 已生成的中间结果不静默覆盖。

### 22.2 Pandoc 失败

- 首先报告 Pandoc error；
- 可配置 fallback MinerU；
- fallback 必须写入 Manifest；
- 不能静默换转换器。

### 22.3 OCR/转换质量异常

V1 不做 AI 自动纠错，但 `inspect/verify` 可输出 warning：

- 超长无标点段落；
- 极端高 forced-split 比例；
- 空白页比例异常；
- MinerU block 缺页；
- 文本长度异常低。

### 22.4 单结构超 hard limit

执行 forced split，并在 metadata 中显式标记。

---

## 23. 日志与可观测性

CLI 面向日常长期使用，必须做到错误可解释。

建议：

- 控制台：简洁进度；
- `logs/processing.jsonl`：结构化事件；
- 每个事件包含 timestamp、stage、document、status、message；
- `--verbose` 输出 adapter/tool command 级信息；
- 默认不在日志写入全文内容。

---

## 24. 安全、隐私与版权边界

### 24.1 本地优先

V1 `docchunk`：

- 不调用外部 LLM API；
- 不主动上传文件；
- MinerU/Pandoc/tiktoken/本地 Python 处理为主。

如果用户的 MinerU 配置本身使用云端后端，那属于 MinerU 环境配置，应由 `doctor` 提示，但 docchunk 不自行启用云服务。

### 24.2 原始资料保护

- 原 source 永不覆盖；
- corpus 生成目录不得写回原文件；
- 不自动删除用户文件；
- cleanup 仅允许删除可再生的中间产物，并应显式操作。

### 24.3 下游版权控制

版权、引用比例、人格模仿等内容由 Cangjie/Nuwa/personal-capability-distiller 各自规则继续管理。docchunk 只保存来源位置，不扩大复制范围。

---

## 25. 性能设计

V1 优先级：正确性 > 可追溯 > 稳定 > 性能。

目标机基线（2026-08-29）：Apple M4（10 核）/ 24GB 统一内存 / macOS 26。V1 串行处理在该配置下足够；处理大型 PDF 前的内存检查遵循 `~/.codex/AGENTS.md` 的 MinerU 资源纪律（资源紧张时降级 pipeline 后端或缩小页范围）。

仍应避免明显低效：

- token count memoization；
- 文件流式读取；
- JSONL 流式写；
- Directory 可按 document 独立 prepare；
- Atomic 生成可以按文档缓存；
- Hash 不变则复用转换结果。

V1 暂不做复杂并发。

原因：MinerU/OCR、文件 IO 与 tokenizer 并发后错误恢复复杂度明显提升，当前主要目标是“每天用都稳”。

后续确认真实吞吐瓶颈后再增加 bounded concurrency。

---

## 26. 测试设计

### 26.1 单元测试

至少覆盖：

- 中文段落边界；
- 中文句号/问号/感叹号；
- 中文分号降级；
- Unicode grapheme；
- Markdown heading；
- list；
- block quote；
- fenced code；
- 普通表格；
- 超大表格；
- forced split；
- tokenizer count；
- Batch overlap；
- natural file sorting；
- source span mapping。

### 26.2 Adapter Fixture

建立固定测试样本：

- 中文课程 TXT；
- 中文 Markdown 书稿；
- DOCX 标题+表格+列表；
- 文本型 PDF；
- 扫描型 PDF；
- MinerU 多页表格；
- 多文件课程目录。

### 26.3 Property / Invariant 测试

重要不变量：

1. Atomic source span 有序；
2. Atomic 无重叠；
3. Atomic 无缺口（排除显式 normalization mapping）；
4. 非 forced split 不突破 hard atomic limit；
5. Batch 中 Atomic 顺序不变；
6. overlap 只由完整 Atomic 构成；
7. Batch 删除 overlap 后，新内容恰好覆盖所有 Atomic；
8. rebuild-batches 不改变 Atomic hash；
9. verify 对人为删除 Atomic 必须失败；
10. 相同输入 + 相同配置 → 相同 logical output/fingerprint。

### 26.4 Golden Tests

对几份固定中文长文档保存期望：

- Atomic 切点；
- Batch 编排；
- heading path；
- PDF 页码；
- forced split flags。

防止未来升级 splitter 后静默改变切片行为。

---

## 27. V1 验收标准

V1 可以宣布完成，至少满足：

### 功能

- [ ] PDF 可通过 MinerU 生成可追页码 Corpus；
- [ ] DOCX 可通过 Pandoc 转换并切片；
- [ ] Markdown/TXT 可直接处理；
- [ ] 目录可作为一个 Document Set；
- [ ] Atomic 按 token + 自然语言边界切分；
- [ ] Atomic 默认无 overlap；
- [ ] Reading Batch 默认约 24K；
- [ ] Batch 默认 overlap 1 个 Atomic；
- [ ] 可生成独立 Markdown；
- [ ] 可生成 `index.jsonl`；
- [ ] 可生成 `manifest.json`；
- [ ] 可追踪 source file / char range / heading / PDF pages；
- [ ] `verify` 可以验证完整性；
- [ ] `rebuild-batches` 不重新切 Atomic；
- [ ] 原 source hash 不变时可复用；
- [ ] 中断后可恢复。

### 质量

- [ ] 不因普通切片截断 UTF-8；
- [ ] 普通中文自然段优先完整保留；
- [ ] 无意外 Atomic 缺口；
- [ ] 无意外 Atomic 重复；
- [ ] overlap 不造成下游无法区分重复上下文；
- [ ] 复杂结构超过 hard limit 时显式标记 forced split；
- [ ] MinerU/Pandoc fallback 不静默发生。

### 集成

- [ ] `longdoc-router` 可以识别 docchunk Corpus；
- [ ] 可按顺序向 Cangjie 提供 batches；
- [ ] 可按 source-separated corpus 向 Nuwa 提供资料；
- [ ] 完成后可将蒸馏结果交给 `personal-capability-distiller`；
- [ ] 不需要修改三个下游 Skill 的源代码。

---

## 28. 明确不进入 V1 的功能

为了避免范围膨胀，以下推迟：

- LLM semantic chunking；
- embedding-based topic segmentation；
- 自动生成章节名称；
- 自动去口语；
- 自动摘要；
- RAG/vector DB；
- Web UI；
- 桌面 GUI；
- 云端任务队列；
- 多 Agent 并发蒸馏；
- 自动下载 YouTube/Bilibili；
- Whisper/ASR；
- EPUB/MOBI 原生解析；
- 自动写入/修改第三方 Skill 源仓库。

这些能力以后可扩展，但不能污染 V1 的核心职责边界。

---

## 29. 后续演进方向

### V1.1 — Input Expansion

- EPUB；
- HTML；
- PPTX；
- 音视频 transcript adapter；
- 更完善的 DOCX provenance。

### V1.2 — Operational Hardening

- 更完整 doctor；
- corpus list/show；
- stale corpus detection；
- 更详细 evidence；
- cleanup policy；
- corruption recovery。

### V1.3 — Profiles & Compatibility

- Codex / Claude / Gemini / Qwen tokenizer profiles；
- 多套 Batch profile 共存；
- downstream adapter registry。

### V1.4 — Topic Navigation

在保持 Atomic 不变的前提下，允许下游 LLM 产生非权威的 logical topic index：

```text
Topic 01 → A001–A019
Topic 02 → A020–A047
```

注意：topic index 是派生认知资产，不改变原始切片。

### V2 — Bounded Concurrency / Corpus Service

只有真实使用中出现大量并行课程/书籍处理需求后，再考虑：

- bounded worker；
- task queue；
- corpus daemon；
- API；
- GUI。

---

## 30. 核心设计决策摘要

| 决策 | V1 选择 |
|---|---|
| 项目核心 | 长文档高质量阅读基础设施，不做新蒸馏器 |
| CLI | `docchunk` |
| Agent 层 | `longdoc-router` Skill |
| PDF | MinerU First |
| DOCX | Pandoc First，必要时 MinerU fallback |
| MD/TXT | Direct |
| 目录 | V1 支持 Document Set |
| Tokenizer | tiktoken，可插拔 |
| OpenAI 默认 encoding | `o200k_base` |
| Atomic | 默认 target 6K，soft 4K–8K |
| Atomic overlap | 无 |
| Batch | 默认 target 24K，soft 16K–32K |
| Batch overlap | 1 个完整 Atomic |
| Hard context profile | 默认 256K，可配置 |
| 核心 splitter | semantic-text-splitter |
| semchunk | Benchmark / future backend |
| LLM 参与切片 | 否 |
| 自动生成主题章节 | docchunk 不做；下游 Skill 可做 |
| 完整性验证 | 必须 |
| SHA / 幂等 | 必须 |
| Resume | 必须 |
| 来源追溯 | 必须 |
| PDF 页码 | 必须，利用 MinerU metadata |
| Cangjie | 上游适配，不 fork |
| Nuwa | 上游适配，不 fork |
| personal-capability-distiller | 最终能力沉淀层 |
| Corpus 与 Obsidian | 物理分离，Obsidian 保存指针 |

---

## 31. 设计结论

`docchunk` 的成功标准不是“把 30 万字切成 20 个文件”，而是：

> 同一份长资料只做一次可靠、可验证的结构化预处理，之后任何模型、任何阅读窗口、任何蒸馏 Skill 都能在不破坏原文、不丢来源、不必重新 OCR/转换的前提下，分批完成高质量阅读。

最终形成清晰的三层体系：

```text
第一层：docchunk
负责“怎么可靠地让 AI 读完”

第二层：Cangjie / Nuwa / 其他成熟 Skill
负责“怎么理解和蒸馏”

第三层：personal-capability-distiller
负责“怎么变成自己的长期能力资产”
```

V1 应坚持克制：把第一层做到稳定、可解释、可验证，比增加更多“智能功能”更重要。

---

## 32. 上游技术选择依据（设计参考）

- `benbrandt/text-splitter` / Python `semantic-text-splitter`：支持 token sizing、容量范围、Unicode sentence/word/grapheme boundary，并有 CommonMark-aware MarkdownSplitter，适合作为 V1 的核心 semantic boundary engine。
- `isaacus-dev/semchunk`：支持 tokenizer/token counter、offsets 与 overlap，适合作为测试基准和未来可插拔 backend；V1 不同时引入两套 runtime splitter。
- `opendatalab/MinerU`：`content_list.json` 提供阅读顺序、`page_idx`、`bbox` 和标题层级信息，适合作为 PDF provenance 的权威来源。
- Pandoc：成熟的文档格式转换 CLI，可进行 DOCX → Markdown，但转换到 Markdown 并不保证保存所有复杂版式，因此原文件 hash 与 provenance 必须保留。
- `kangarooking/cangjie-skill`：继续作为书籍、课程、视频/播客文字稿的方法论蒸馏器；docchunk 只替换其“超长原文如何稳定分批读取”的基础设施。
- `alchaincyf/nuwa-skill`：继续负责人物认知框架/决策逻辑/表达 DNA 蒸馏；docchunk 提供多来源 Corpus。
- `hg199074jin/personal-capability-distiller`：继续作为个人能力卡、候选 Skill、验证、Obsidian 归档和能力树的最终沉淀层。

---

## 33. 本机环境基线（2026-08-29 核实）

| 项目 | 事实 |
|---|---|
| 机型 / 芯片 / 内存 | Apple M4（10 核）/ 24GB 统一内存 |
| 系统 | macOS 26.5.1（arm64） |
| 内置盘 | 460GB，可用 372GB |
| 外接盘 | `/Volumes/ORICO`，954GB APFS，可用 949GB；项目仓库与 MinerU 模型同盘 |
| Python | 3.12.14（uv 管理，默认 `python3`） |
| uv / git / gh | uv 0.12.5 / git 2.55 / gh 2.97.0（已登录 hg199074jin，git 协议 ssh） |
| MinerU | 3.4.5 @ `~/.venvs/mineru/bin/mineru`（不在 PATH）；模型在 `/Volumes/ORICO/Data/mineru-models`；默认 backend `hybrid-engine` + `--effort medium` |
| Pandoc | 3.11 @ `/usr/local/bin/pandoc`（官方 pkg，在 PATH；AGENTS.md 第 16 节禁止 brew 重装） |
| tiktoken 网络 | `openaipublic.blob.core.windows.net` 与 PyPI 经代理可达 |
| 仓库位置 | `/Volumes/ORICO/Projects/docchunk`（原始文档在 `doc/` 下） |
| Corpus 根目录 | 默认 `/Volumes/ORICO/LongDocCorpus`（2026-08-29 确认） |

