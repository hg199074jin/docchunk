# DocChunk Page-Level Smart PDF Routing 设计文档

**项目：** `hg199074jin/docchunk`  
**功能名称：** Page-Level Smart PDF Routing  
**建议版本：** v1.1.0  
**设计状态：** Final Design  
**核心原则：** 能可靠直接读取的文字不 OCR；只有不能可靠读取的页面才使用 MinerU  
**优先级：** 准确性 > 完整性 > 可追溯性 > 稳定性 > 处理速度

> **本机适配与实测记录（2026-08-31，Apple M4 / MinerU 3.4.5）**
>
> 1. `pdf-inspector` 已核实真实存在：PyPI 1.17.0（Firecrawl，MIT，Rust/PyO3，**零运行时依赖**，macOS arm64 wheel，自带 `.pyi` 类型标注）。`detect_pdf` / `extract_pages_markdown` / `pages=` 过滤参数与本设计假设逐字段吻合。
> 2. 本机 MinerU 3.4.5 已核实支持 `--start` / `--end`（0-based，`--end` 含端点）。
> 3. 实测关键证据：本仓库 tests 内 52 页扫描合同 PDF，`detect_pdf` 判为 `text_based`（confidence 0.75、0 页需 OCR），但逐页真实提取 **52/52 全部 `needs_ocr=True, reason=scanned, 0 字符`**（47ms）。→ §10「分类只做诊断、路由以提取期 `needs_ocr` 为准」被真实文件证明为必需。
> 4. **方案 A（用户已确认，2026-08-31）**：当所有页面都被判定 `needs_ocr`（纯扫描 PDF）时，直接整份调用一次 `MinerUAdapter.prepare()`（`parser_route=mineru_only`），不做逐页调用；`page-routing.jsonl` 仍每页一行 `parser=mineru`。混合 PDF 仍严格逐页。理由：M4 上每次 MinerU 调用都重新加载模型，52 页合同逐页调用估算 30–60 分钟，整份一次调用实测量级为 13 分钟/293 页。
> 5. pdf-inspector 页码/字段的真实约定见 §33（已按 1.17.0 实测核实）。

---

# 1. 背景

DocChunk 当前对于 PDF 的处理逻辑较为简单：

```text
PDF
 ↓
MinerUAdapter
 ↓
MinerU
 ↓
Markdown
 ↓
NormalizedDocument
 ↓
Atomic Chunk
 ↓
Batch
```

即所有 `.pdf` 文件统一交给 MinerU。

这一方案虽然简单，但并不适合大量现实文档。

例如一份 100 页审计报告：

```text
第 1–3 页
审计报告正文、注册会计师签章
→ 扫描页面

第 4–100 页
财务报表及财务报表附注
→ 原生电子文字 PDF
```

如果因为前三页是扫描件，就把整份 100 页 PDF 全部重新解析甚至 OCR，并不一定能获得更准确的结果。

对于已经存在可靠文字层的页面：

```text
PDF 原生文字
→ 直接提取
```

通常比：

```text
PDF 原生文字
→ 图像/视觉解析
→ OCR
→ 再恢复文字
```

少一次信息转换，也就少一次引入错误的机会。

尤其对于：

- 财务报表数字；
- 审计底稿；
- 合同金额；
- 日期；
- 法律条款；
- 财务报表附注；

准确性比处理速度更加重要。

因此 DocChunk 的 PDF 策略需要从：

> Document-Level Parser Selection

升级为：

> **Page-Level Parser Selection**

---

# 2. 核心设计原则

正式确定以下原则：

> **能可靠直接读取的页面，使用 PDF 原生文字。**
>
> **只有需要 OCR 的页面，才交给 MinerU。**

处理速度不是该功能的主要决策依据。

减少 MinerU 调用只是结果，不是目标。

真正目标是：

> 尽量减少不必要的信息转换，在保证完整性的前提下获得更准确的文档内容。

---

# 3. 不使用 pdf-inspector 自带 OCR

正式确定：

```text
pdf-inspector OCR
→ 不使用
```

两套工具职责明确分离。

## pdf-inspector

负责：

```text
PDF inspection
PDF page classification
Native text extraction
Markdown conversion
Page OCR recommendation
Encoding issue detection
Table / column detection
```

## MinerU

负责：

```text
扫描页 OCR
图片型页面
原生文字不可可靠读取页面
pdf-inspector native extraction 失败页面
```

DocChunk 不同时维护两套 OCR runtime。

---

# 4. 最终总体架构

```text
                         PDF
                          │
                          ▼
                 SmartPdfAdapter
                          │
                          ▼
                pdf-inspector 全文检查
                          │
                          ▼
                  Page Routing Table
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
      Native-safe Pages           OCR-required Pages
             │                         │
             ▼                         ▼
      pdf-inspector                  MinerU
      native Markdown               OCR Markdown
             │                         │
             └────────────┬────────────┘
                          ▼
                    Page Assembler
                          │
                          ▼
                  NormalizedDocument
                          │
                          ▼
                     DocChunk
                          │
                    Atomic Chunk
                          │
                        Batch
```

---

# 5. PDF 的入口发生变化

当前：

```text
.pdf
 ↓
MinerUAdapter
```

修改为：

```text
.pdf
 ↓
SmartPdfAdapter
```

因此：

```python
choose_adapter(...)
```

未来对于 PDF 返回：

```text
SmartPdfAdapter
```

而不是：

```text
MinerUAdapter
```

---

# 6. 新增组件

建议增加：

```text
src/docchunk/adapters/

├── pdf.py
├── pdf_inspector.py
├── mineru.py
└── ...
```

其中：

## `pdf.py`

负责：

```text
SmartPdfAdapter
Page Routing
Page Assembly
Fallback coordination
```

## `pdf_inspector.py`

负责：

```text
pdf-inspector Python API
Native page extraction
Inspection result normalization
```

## `mineru.py`

继续负责 MinerU。

同时扩展：

```text
单页 PDF 解析能力
```

---

# 7. PDF 预检

SmartPdfAdapter 首先执行：

```python
pdf_inspector.detect_pdf(...)
```

获取文档级信息：

```text
pdf_type
pdf_type_confidence
page_count
pages_needing_ocr
ocr_reasons_by_page
has_encoding_issues
is_complex_layout
pages_with_tables
pages_with_columns
```

这些信息主要用于：

- 初步判断；
- metadata；
- 日志；
- inspect；
- 可解释性。

---

# 8. confidence 的正式定义

保存：

```text
pdf_type_confidence
```

不保存模糊的：

```text
confidence
```

因为这个值表示：

> pdf-inspector 对 PDF 类型分类结果的置信程度。

它不是：

- OCR 文字准确率；
- Markdown 准确率；
- 内容完整率。

因此：

```text
pdf_type_confidence
```

**不设置路由阈值。**

禁止：

```text
confidence >= 0.8
→ native
```

也禁止：

```text
confidence < 0.8
→ MinerU
```

confidence 只作为诊断信息保存。

---

# 9. 全文逐页 Native Extraction

检测完成后，再执行：

```python
pdf_inspector.extract_pages_markdown(...)
```

对 PDF 所有页面实际执行 native extraction。

不是只抽取前几页。

最终获得：

```text
PageMarkdown[]
```

每页至少包含：

```text
page
markdown
needs_ocr
ocr_reason
```

这里：

```text
PageMarkdown.page
```

是：

```text
0-based
```

正好与 DocChunk 当前：

```text
NormalizedBlock.page_idx
```

保持一致。

---

# 10. 真正的路由单位是 Page

以后：

```text
TextBased
Mixed
Scanned
ImageBased
```

仍然保留。

但这些只是：

```text
Document Classification
```

不是最终 parser 决策。

真正的路由单位：

> **Page**

例如：

```text
审计报告.pdf

Page 1  → MinerU
Page 2  → MinerU
Page 3  → MinerU

Page 4  → pdf-inspector
Page 5  → pdf-inspector
...
Page 100 → pdf-inspector
```

最终文档虽然属于：

```text
Mixed
```

但不因此整份 MinerU。

---

# 11. Page Routing Rule

V1.1 路由规则保持简单。

对于每一页：

```text
needs_ocr == false
        ↓
pdf-inspector native
```

如果：

```text
needs_ocr == true
```

则：

```text
MinerU
```

因此核心规则只有：

```python
if page.needs_ocr:
    route = "mineru"
else:
    route = "native"
```

不额外因为：

```text
table
column
复杂布局
```

自动触发 MinerU。

---

# 12. Encoding Issues

如果：

```text
has_encoding_issues == true
```

优先依据：

```text
ocr_reasons_by_page
pages_needing_ocr
```

定位具体异常页面。

只有这些页面：

```text
→ MinerU
```

其余可以可靠读取的页面：

```text
→ native
```

如果出现极少见的情况：

```text
has_encoding_issues = true

但

无法确定具体异常页面
```

则采用保守策略：

```text
整份 PDF → MinerU
```

并记录：

```text
route_reason =
unlocalized_encoding_issue
```

准确性优先于避免 MinerU。

---

# 13. 复杂表格不自动 MinerU

正式确定：

```text
pages_with_tables != []
```

不构成 MinerU 路由条件。

例如：

```text
Page 20

native text: OK
table detected: Yes
needs_ocr: False
```

仍然：

```text
pdf-inspector
```

原因是 pdf-inspector 本身已经支持：

- table detection；
- Markdown table；
- reading order；
- layout-aware extraction。

因此不能简单使用：

```text
有表格 = MinerU
```

这种规则。

---

# 14. 多栏页面同样处理

如果：

```text
pages_with_columns != []
```

但：

```text
needs_ocr = false
```

仍然使用：

```text
pdf-inspector
```

多栏只作为 metadata。

不是 OCR 条件。

---

# 15. MinerU 单页处理

对于被判定为：

```text
needs_ocr
```

的页面，不物理拆分原始 PDF。

直接调用原 PDF：

```text
mineru \
  -p original.pdf \
  -o TEMP \
  --start N \
  --end N
```

其中：

```text
N = 原 PDF 的 0-based page index
```

MinerU 当前正式 CLI 已支持：

```text
--start
--end
```

因此可以直接指定原文件页面。

> 本机适配记录：MinerU 3.4.5 `--help` 实测确认 `-s/--start`、`-e/--end`（INTEGER，"beginning from 0"）。本机 MinerU 位于 `~/.venvs/mineru/bin/mineru`（不在 PATH），统一经 `resolve_mineru_command()` 解析，不写死路径。

---

# 16. 为什么 V1.1 默认逐页调用 MinerU

例如：

```text
OCR Pages:

0
1
2
37
84
85
```

理论上可以合并：

```text
0–2
37
84–85
```

然后分三次调用 MinerU。

V1.1 暂时不做这一优化。

推荐：

```text
Page 0 → MinerU
Page 1 → MinerU
Page 2 → MinerU
...
```

即：

> 一个 OCR page，一次 MinerU page parse。

原因不是性能。

而是为了：

- 页码映射绝对明确；
- provenance 简单；
- 不依赖 MinerU range output 的 page index 行为；
- 错误定位简单；
- 单页失败容易发现；
- assembler 不需要推断页面对应关系。

处理速度不是当前优先级，因此暂不为减少 MinerU 调用增加额外复杂度。

以后可以在不改变接口的情况下优化成 range batching。

## 16.1 方案 A：纯扫描 PDF 走整份单次调用（2026-08-31 用户确认）

当逐页提取结果显示**所有页面**都是：

```text
needs_ocr == true
```

即整份 PDF 没有任何一页可以可靠原生读取时，逐页调用只意味着把同一次模型加载重复 N 遍，不带来任何准确性收益。

此时改为：

```text
MinerUAdapter.prepare(original.pdf)
```

整份一次调用完成，并记录：

```text
parser_route = mineru_only
```

约束：

- `page-routing.jsonl` 仍必须每页一行，`parser = mineru`；
- 页码 provenance 走现有 content_list 对齐（`align_blocks_to_markdown`），与 V1 整份路径一致；
- 逐页调用规则（本节上文）仅适用于**混合 PDF**（存在至少一页 native-safe）；
- 单页失败语义不变：整份调用失败即 prepare 失败，禁止静默降级。

实测依据：52 页扫描合同逐页路径需 52 次模型加载（估算 30–60 分钟），整份路径与 V1 蓝书 293 页 13 分钟同量级。

---

# 17. MinerU Page Index

即使 MinerU 输出自己的：

```text
page_idx
```

SmartPdfAdapter 也不依赖它确定最终页码。

例如：

```text
原 PDF Page 37
```

调用：

```text
--start 37
--end 37
```

则最终所有该次 MinerU 产生的 block：

```text
page_idx = 37
```

由 DocChunk 强制赋值。

这样不会受到 MinerU：

```text
返回 0
还是
返回 37
```

的内部实现影响。

原 PDF 页码是唯一权威来源。

---

# 18. 新增 PageFragment

建议增加内部模型：

```text
PageFragment
```

概念结构：

```text
page_idx
markdown
blocks
parser
route_reason
metadata
```

例如：

```text
PageFragment

page_idx: 37
parser: mineru
route_reason: scanned
markdown: "……"
```

或者：

```text
page_idx: 38
parser: pdf_inspector
route_reason: native_text_safe
markdown: "……"
```

PageFragment 是：

```text
Parser
```

和：

```text
NormalizedDocument
```

之间的中间结构。

---

# 19. Native Page Block

pdf-inspector native 页面初期不必转成大量细粒度 text items。

一个页面至少生成一个：

```text
NormalizedBlock
```

例如：

```text
block_index = ...
page_idx = 38
text = page_markdown
```

这样已经足够支持：

```text
Atomic Chunk
→ page_start
→ page_end
```

---

# 20. MinerU Block

MinerU 单页处理仍然可以保留：

```text
content_list
```

中的细粒度 block。

但 SmartPdfAdapter 必须：

```text
把 block.page_idx
统一重写为真实 original page_idx
```

这样保留：

- bbox；
- heading level；
- text blocks；

同时保证来源页绝对准确。

---

# 21. Page Assembler

所有页面处理完成后：

```text
PageFragment 0
PageFragment 1
PageFragment 2
...
```

按：

```text
page_idx ASC
```

排序。

然后组装：

```text
NormalizedDocument
```

---

# 22. Markdown 合并

页面 Markdown 之间统一：

```text
\n\n
```

连接。

例如：

```text
Page 1 Markdown

Page 2 Markdown

Page 3 Markdown
```

禁止写入人工标记：

```text
--- Page 1 ---

# PAGE 1

<!-- Page -->
```

因为这些不是原文内容。

它们会污染：

- Token；
- hash；
- chunk；
- semantic splitting。

页码由 provenance 保存。

---

# 23. Block Offset 重计算

PageFragment 内 block 的：

```text
char_start
char_end
```

是页面内部 offset。

Assembler 合并时统一转换为：

```text
document-global offset
```

例如：

```text
Page 0

0–2000

Page separator

Page 1

2002–5300
```

这样最终：

```text
NormalizedBlock
```

仍然符合当前 DocChunk 数据模型。

---

# 24. Blank Page

空白页不能简单认为解析失败。

例如：

```text
Page 26

needs_ocr = false
markdown = ""
```

可以是真正的空白页。

此时：

```text
保留页面路由记录
```

但不必产生正文 block。

如果：

```text
needs_ocr = true
markdown = ""
```

则：

```text
MinerU
```

---

# 25. Native Extraction Failure

例如：

```text
Page 52

检测：
native safe

但是：
extract_pages_markdown 执行失败
```

则不是整份失败。

只把：

```text
Page 52
```

重新路由：

```text
MinerU
```

route_reason：

```text
native_extraction_failed
```

其余页面继续使用 native。

---

# 26. pdf-inspector 整体失败

如果 pdf-inspector 连：

```text
page_count
```

或：

```text
page inventory
```

都无法可靠取得：

此时不能做 page-level routing。

采用：

```text
Whole PDF
    ↓
MinerUAdapter
```

记录：

```text
parser_route =
full_mineru_fallback

route_reason =
pdf_inspector_failed
```

---

# 27. Page Count 不一致

如果：

```text
detect_pdf.page_count = 100
```

但：

```text
extract_pages_markdown
```

只返回：

```text
99 pages
```

属于结构性异常。

禁止继续自行猜测缺失页面。

直接：

```text
Whole PDF
→ MinerU
```

route_reason：

```text
page_inventory_mismatch
```

---

# 28. MinerU 单页失败

例如：

```text
Page 3
needs_ocr = true
```

MinerU 处理该页失败。

禁止退回：

```text
pdf-inspector 原生结果
```

因为该页已经被判定：

```text
native unreliable
```

此时：

```text
整个 prepare 失败
```

抛出：

```text
ExternalToolError
```

并明确显示：

```text
file
page_number
route_reason
MinerU error
```

准确性优先。

宁可失败，也不静默使用已知不可靠的文字。

---

# 29. Document Route 类型

最终文档增加：

```text
parser_route
```

建议值：

```text
native_only
mineru_only
mixed
full_mineru_fallback
```

例如审计报告：

```text
native pages: 97
mineru pages: 3
```

则：

```text
parser_route = mixed
```

> 方案 A：`mineru_only` 由纯扫描 PDF 的整份单次 `MinerUAdapter.prepare()` 产生（见 §16.1）；逐页路径只会产生 `native_only` 或 `mixed`。`full_mineru_fallback` 仅由 §26/§27 的兜底场景产生。

---

# 30. 不把所有 Page Route 塞进 source-ref.json

100 页甚至 1000 页 PDF 如果把每页 metadata 全放：

```text
source-ref.json
```

会造成文件和 Manifest 膨胀。

因此增加：

```text
page-routing.jsonl
```

路径：

```text
source/
└── documents/
    └── D0001/
        ├── normalized.md
        ├── blocks.jsonl
        ├── source-ref.json
        └── page-routing.jsonl
```

---

# 31. page-routing.jsonl

每页一条记录。

例如：

```json
{
  "page_idx": 0,
  "page_number": 1,
  "parser": "mineru",
  "route_reason": "scanned",
  "needs_ocr": true
}
```

第二页：

```json
{
  "page_idx": 1,
  "page_number": 2,
  "parser": "mineru",
  "route_reason": "scanned",
  "needs_ocr": true
}
```

第 4 页：

```json
{
  "page_idx": 3,
  "page_number": 4,
  "parser": "pdf_inspector",
  "route_reason": "native_text_safe",
  "needs_ocr": false
}
```

---

# 32. Page Number 规则

明确规定：

内部：

```text
page_idx
= 0-based
```

用户显示：

```text
page_number
= 1-based
```

例如：

```text
page_idx = 0
page_number = 1
```

所有转换统一由一个 helper 完成。

禁止各模块自行：

```text
+1 / -1
```

避免 off-by-one 错误。

---

# 33. 特别注意 pdf-inspector 的页码 API 差异

pdf-inspector 当前不同 API 对页号存在差异。

因此 DocChunk 不允许在业务代码中直接传播外部页码。

所有 pdf-inspector 返回值必须首先转换为：

```text
DocChunk internal page_idx
```

内部统一：

```text
0-based
```

再参与 Page Routing。

这是必须有自动测试保护的边界。

## 33.1 pdf-inspector 1.17.0 实测页码约定表

| API / 字段 | 页码基准 | 说明 |
|---|---|---|
| `extract_pages_markdown()` → `PageMarkdown.page` | **0-based** | 与内部 `page_idx` 直接同基 |
| `detect_pdf()` → `PdfResult.pages_needing_ocr` | **1-based** | 需 −1 转内部 page_idx |
| `detect_pdf()` → `PdfResult.ocr_reasons_by_page[].page` | **1-based** | 需 −1 转内部 page_idx |
| `extract_pages_markdown()` → `PagesExtractionResult.pages_needing_ocr` | **1-based** | 需 −1 转内部 page_idx |
| `extract_pages_markdown()` → `pages_with_tables` / `pages_with_columns` | **1-based** | 作为用户可读 metadata 保存，保持 1-based |
| `extract_pages_markdown(path, pages=[...])` 过滤参数 | **0-based** | 单页重试时直接传内部 page_idx |

同一次 `extract_pages_markdown` 返回内部就混用两种基准（`PageMarkdown.page` 0-based，顶层清单 1-based），这是必须集中转换、禁止散落 `+1/-1` 的直接原因。

## 33.2 pdf-inspector 1.17.0 字段形状差异

- 提取期每页是 `ocr_reason`（**单数** `str | None`）；检测期 `ocr_reasons_by_page[].reasons` 是**复数** `list[str]`。归一化规则：提取期 `needs_ocr` 为路由权威；`NativePageResult.ocr_reasons: list[str]` 由单数 `ocr_reason` 包装成单元素列表，再合并检测期对应页的 reasons 作为诊断信息（去重保序）。
- `detect_pdf` 返回 `is_complex_layout`，`extract_pages_markdown` 返回 `is_complex`——两个字段名不同。`PdfInspectionSummary.is_complex_layout` 统一取 detect 结果；extract 侧的 `is_complex` 不写入 summary。
- `PagesExtractionResult` **没有 `page_count` 字段**：页清单完整性校验必须以 `detect_pdf().page_count` 为基准，对比实际返回页数（§27）。

---

# 34. source-ref.json

建议最终：

```json
{
  "adapter": "smart_pdf",
  "parser_route": "mixed",
  "pdf_inspection": {
    "engine": "pdf-inspector",
    "pdf_type": "mixed",
    "pdf_type_confidence": 0.7,
    "page_count": 100,
    "has_encoding_issues": false,
    "is_complex_layout": true,
    "pages_with_tables": [5, 6, 20],
    "pages_with_columns": []
  },
  "routing": {
    "policy": "page_smart_v1",
    "native_pages": 97,
    "mineru_pages": 3,
    "page_routing_path": "source/documents/D0001/page-routing.jsonl"
  }
}
```

---

# 35. adapter 字段

因为最终文档实际上是两个 parser 拼装的：

不再写：

```text
adapter = pdf_inspector
```

或者：

```text
adapter = mineru
```

Mixed PDF 应写：

```text
adapter = smart_pdf
```

具体页面 parser 在：

```text
page-routing.jsonl
```

保存。

---

# 36. Page Provenance 通用化

当前：

```text
source_pages_for_span()
```

虽然位于：

```text
provenance/mineru.py
```

实际上只依赖：

```text
NormalizedBlock.page_idx
```

因此建议迁移：

```text
provenance/pages.py
```

形成通用：

```text
Page Provenance
```

这样：

```text
pdf-inspector block
MinerU block
```

都走同一套：

```text
page_start
page_end
```

计算。

---

# 37. inspect 命令

以后：

```bash
docchunk inspect report.pdf
```

应该执行完整的：

```text
PDF native preflight
```

但不真正调用 MinerU。

例如：

```text
PDF Inspection
--------------

file:
audit-report.pdf

type:
mixed

pages:
100

planned routing:

native:
97

mineru:
3

OCR pages:
1-3

tables:
5, 7, 9, 20

encoding issues:
false

route policy:
page_smart_v1
```

这样用户在真正 split 前就能知道：

```text
哪些页会使用 OCR。
```

---

# 38. doctor

增加：

```text
pdf-inspector
```

检查。

最终：

```text
OK python
OK pdf-inspector
OK pandoc
OK mineru
OK tiktoken
OK corpus_root
```

pdf-inspector 是 Python dependency。

MinerU 仍然是外部能力。

---

# 39. Dependency

`pyproject.toml` 增加：

```text
pdf-inspector
```

作为正式 dependency。

不是 optional。

因为以后：

```text
SmartPdfAdapter
```

是所有 PDF 的正式入口。

---

# 40. Normalization Fingerprint

这个功能会直接改变 normalized Markdown。

因此 normalization fingerprint 必须升级。

增加：

```text
pdf_policy = page_smart_v1
pdf_inspector_version
mineru_version
mineru_backend
mineru_effort
mineru_page_method
```

例如：

```json
{
  "pdf_policy": "page_smart_v1",
  "pdf_inspector_version": "1.x.x",
  "mineru_version": "3.x.x",
  "mineru_backend": "hybrid-engine",
  "mineru_effort": "medium",
  "mineru_page_method": "ocr"
}
```

这样旧版：

```text
PDF → Entire MinerU
```

产生的 normalized cache 不会被新版误用。

---

# 41. Routing Policy Version

定义：

```text
PAGE_SMART_PDF_POLICY_VERSION =
"page_smart_v1"
```

以后路由策略变化：

```text
page_smart_v2
```

自动触发 normalization rebuild。

---

# 42. 日志

增加：

```text
pdf_inspection
pdf_page_route
pdf_page_fallback
pdf_assembly
```

事件。

例如：

```text
Page 1:
mineru
reason=scanned

Page 2:
mineru
reason=scanned

Page 4:
pdf_inspector
reason=native_text_safe
```

不用默认在 console 输出 1000 行。

详细记录进入：

```text
processing.jsonl
```

console 只显示 summary。

---

# 43. 临时文件

MinerU 单页处理使用独立临时目录。

例如：

```text
docchunk-mineru-page-0001-xxxx/
```

处理结束：

```text
自动删除
```

无论：

```text
success
failure
```

都必须清理。

原 PDF：

```text
永远只读
```

---

# 44. 测试：最关键场景

新增：

```text
tests/test_pdf_router.py
tests/test_pdf_inspector_adapter.py
tests/test_pdf_page_assembler.py
```

---

## Case 1：纯电子 PDF

```text
10 pages
全部 native
```

结果：

```text
pdf-inspector = 10
MinerU = 0
parser_route = native_only
```

---

## Case 2：纯扫描 PDF

```text
10 pages
全部 needs_ocr
```

结果：

```text
MinerU = 10
parser_route = mineru_only
```

> 方案 A（§16.1）：纯扫描 PDF 由整份单次 `MinerUAdapter.prepare()` 完成（1 次调用，非 10 次逐页），`page-routing.jsonl` 仍 10 行、每行 `parser=mineru`。

---

## Case 3：审计报告

最重要的真实业务 fixture：

```text
100 pages

Page 1–3:
scanned

Page 4–100:
native
```

期望：

```text
MinerU = 3 pages
pdf-inspector = 97 pages

parser_route = mixed
```

最终页码：

```text
1–100
```

必须连续、准确。

---

## Case 4：中间扫描附件

```text
Pages 1–20 native

Page 21 scanned

Pages 22–50 native
```

最终：

```text
Page 21 → MinerU
```

其他不受影响。

---

## Case 5：复杂表格

```text
Page 20:
table = yes
needs_ocr = false
```

必须：

```text
pdf-inspector
```

不能因为表格自动 MinerU。

---

## Case 6：多栏

```text
columns = yes
needs_ocr = false
```

仍然：

```text
pdf-inspector
```

---

## Case 7：Encoding Issue

如果定位到：

```text
Page 32
```

只有：

```text
Page 32
→ MinerU
```

---

## Case 8：Native Extraction Failure

```text
Page 18 native extraction exception
```

只：

```text
Page 18 → MinerU
```

---

## Case 9：MinerU Failure

```text
Page 3 requires OCR
MinerU fails
```

整个 prepare：

```text
FAILED
```

禁止使用不可靠 native 内容顶替。

---

## Case 10：Page Inventory Mismatch

```text
PDF page_count = 100

extract result = 99
```

不得自行推断。

整份：

```text
MinerU fallback
```

---

# 45. 验收指标

V1.1 完成后必须满足：

1. PDF 不再无条件调用 MinerU。
2. 每个 PDF 都先经过 pdf-inspector。
3. 所有页面都经过 page-level native extraction 检查。
4. native-safe 页面直接使用原生文字。
5. needs_ocr 页面单独交给 MinerU。
6. Mixed PDF 可以同时包含 native 和 OCR 页面。
7. MinerU OCR 页面不需要物理拆分 PDF。
8. MinerU page number 由 DocChunk 自己保证。
9. `confidence` 不参与阈值路由。
10. 表格不自动触发 MinerU。
11. 多栏不自动触发 MinerU。
12. pdf-inspector 自带 OCR 不启用。
13. MinerU page failure 不得静默降级。
14. Page provenance 不丢失。
15. Atomic Chunk 的 page_start/page_end 保持准确。
16. source-ref 可以知道整个 PDF 使用了什么策略。
17. page-routing.jsonl 可以追溯每一页使用了哪个 parser。
18. normalization fingerprint 能识别新旧 PDF pipeline。
19. 原始 PDF 永远不修改。
20. 原有 DocChunk verify 能继续验证最终 Corpus。
21. 纯扫描 PDF（所有页 needs_ocr）由整份单次 MinerU 调用完成（方案 A，§16.1），page-routing.jsonl 仍每页一行。

---

# 46. 最终架构

```text
TXT
 │
 └────→ TextAdapter


Markdown
 │
 └────→ MarkdownAdapter


DOCX
 │
 └────→ PandocAdapter
             │
             └── optional fallback


PDF
 │
 ▼
SmartPdfAdapter
 │
 ▼
pdf-inspector
Full Page Inspection
 │
 ▼
Page Router
 │
 ├──────── native-safe page
 │              │
 │              ▼
 │       pdf-inspector Markdown
 │
 └──────── OCR-required page
                │
                ▼
             MinerU
         --start N --end N
                │
                ▼
           OCR Markdown

                ↓

          Page Assembler

                ↓

       NormalizedDocument

                ↓

        Atomic → Batch
```

---

# 47. 最终设计结论

DocChunk 不再把：

```text
PDF
```

视为一个只能选择一种 parser 的整体。

新的处理理念是：

> **一个 PDF 是由若干页面组成的文档，每一页都应该根据自身的信息形态选择最可靠的读取方式。**

因此：

```text
原生文字页面
→ 直接读取原生文字

扫描页面
→ MinerU OCR

混合 PDF
→ 两种结果按原始页码重新组合
```

最终目标不是：

> 少调用 MinerU。

也不是：

> 尽可能提高处理速度。

而是：

> **尽可能保留 PDF 中本来就正确的信息，只在确实无法可靠直接读取时才增加 OCR 这一层转换。**

对于审计报告、财务报表、合同、政策文件等对数字和文字准确性要求较高的资料，这是比“整份 PDF 统一 OCR/统一解析”更合理的处理策略。