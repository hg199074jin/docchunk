# DocChunk Page-Level Smart PDF Routing 实施方案

> **本机适配与决策记录（2026-08-31，Apple M4 / MinerU 3.4.5，用户确认）**
>
> 1. 基线已核实：`main@3cbb894` 工作区干净，60 tests / ruff / mypy 全绿。
> 2. `pdf-inspector==1.17.0` 已核实存在且与本文 API 假设逐字段吻合（MIT、零运行时依赖、arm64 wheel、带 `.pyi`）。本机直连 PyPI 的 `uv` 可能报 TLS handshake eof（curl 正常），届时用 `uv --native-tls` 重试或 `curl` 下载 wheel 本地安装。
> 3. 本机 MinerU 3.4.5 已核实支持 `--start` / `--end`（0-based，含端点）；MinerU 路径统一经 `resolve_mineru_command()` 解析（`~/.venvs/mineru/bin/mineru`）。
> 4. **方案 A（用户已确认）**：所有页 `needs_ocr` 的纯扫描 PDF 直接整份 `MinerUAdapter.prepare()` 一次调用（`parser_route=mineru_only`），不做逐页调用；混合 PDF 仍严格逐页。依据：52 页扫描合同逐页路径 = 52 次模型加载（估算 30–60 分钟），整份路径实测量级 13 分钟/293 页。详见设计文档 §16.1。
> 5. pdf-inspector 1.17.0 页码/字段实测约定见「Task 4」前的补充节，实现时必须遵守。

## 实施目标

将 DocChunk 当前：

```text
PDF
↓
MinerU
↓
NormalizedDocument
```

升级为：

```text
PDF
 ↓
pdf-inspector 全页检查
 ↓
逐页判断
 ├─ 可可靠直接读取 → pdf-inspector
 └─ 需要 OCR       → MinerU 指定该页
 ↓
按原始页码重新组装
 ↓
NormalizedDocument
 ↓
Atomic → Batch
```

核心原则固定为：

> **能可靠直接读取的页面不 OCR；只有不能可靠直接读取的页面才使用 MinerU。**

优先级：

> **准确性 > 完整性 > 可追溯性 > 稳定性 > 速度**

---

## 本次明确不做的事情

1. 不使用 pdf-inspector 自带 OCR。
2. 不设置 confidence 路由阈值。
3. 不因为有表格就强制 MinerU。
4. 不因为有多栏就强制 MinerU。
5. 不因为 PDF 是 Mixed 就整份 MinerU。
6. 不为了提高速度合并多个 OCR 页批量处理。
7. 暂不做并发页解析。
8. 暂不设计“数字保留率”等复杂质量评分。
9. 不改变 Atomic / Batch token policy。
10. 不把真实审计资料加入公开测试 fixture。

---

# 实施顺序

整个工作拆成 14 个任务。

## Task 1：增加 pdf-inspector 依赖和 PDF 内部模型

修改：

```text
pyproject.toml
uv.lock
```

新建：

```text
src/docchunk/models/pdf.py
tests/test_pdf_models.py
```

新增依赖：

```toml
"pdf-inspector>=1.17.0,<2",
```

内部定义：

```python
PdfInspectionSummary
NativePageResult
PdfPageRoute
PageFragment
PdfInspectorBundle
```

并建立唯一的页码转换：

```python
def page_index_to_number(page_idx: int) -> int:
    if page_idx < 0:
        raise ValueError("page_idx must be >= 0")
    return page_idx + 1


def page_number_to_index(page_number: int) -> int:
    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    return page_number - 1
```

整个项目以后禁止散落：

```python
page + 1
page - 1
```

这种转换。

业务层只认：

```text
page_idx = 0-based
```

用户输出才转换为：

```text
page_number = 1-based
```

---

## Task 2：把 Page Provenance 从 MinerU 中独立出来

当前：

```text
src/docchunk/provenance/mineru.py
```

里的：

```python
source_pages_for_span()
```

实际上不是 MinerU 专属逻辑。

迁移到：

```text
src/docchunk/provenance/pages.py
```

以后：

```text
MinerU page block
        │
        ├──→ source_pages_for_span()
        │
pdf-inspector page block
        │
        └──→ source_pages_for_span()
```

这样 Atomic Chunk 的：

```text
page_start
page_end
```

不再依赖具体 PDF parser。

---

## Task 3：给 NormalizedDocument 增加 sidecar 能力

原因是：

```text
page-routing.jsonl
```

不能把全部内容塞进：

```text
source-ref.json
manifest.json
```

否则几百页 PDF 会让 metadata 膨胀。

因此建议：

```python
class NormalizedDocument(BaseModel):
    source_path: Path
    media_type: str
    text: str
    blocks: list[NormalizedBlock] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    sidecars: dict[str, str] = Field(default_factory=dict)
```

Smart PDF 最后返回：

```python
sidecars={
    "page-routing.jsonl": "...逐页 JSONL..."
}
```

pipeline 负责写到：

```text
source/documents/D0001/

├── normalized.md
├── blocks.jsonl
├── source-ref.json
└── page-routing.jsonl
```

adapter 本身不知道 Corpus 路径。

这是职责边界最干净的方案。

---

## pdf-inspector 1.17.0 实测约定（Task 4 实现时必须遵守）

页码基准（库内混用，必须集中转换）：

| API / 字段 | 页码基准 | 处理 |
|---|---|---|
| `PageMarkdown.page` | 0-based | 直接作内部 `page_idx` |
| `PdfResult.pages_needing_ocr` | 1-based | −1 转内部 |
| `ocr_reasons_by_page[].page` | 1-based | −1 转内部 |
| `PagesExtractionResult.pages_needing_ocr` | 1-based | −1 转内部 |
| `pages_with_tables` / `pages_with_columns` | 1-based | 保持 1-based 作为用户可读 metadata |
| `extract_pages_markdown(pages=[...])` 过滤参数 | 0-based | 单页重试直接传 `page_idx` |

字段形状差异：

- 提取期每页 `ocr_reason` 是**单数** `str | None`；检测期 `reasons` 是**复数** `list[str]`。归一化：提取期 `needs_ocr` 为路由权威；`NativePageResult.ocr_reasons` = 单数包装成列表 ∪ 检测期对应页 reasons（去重保序）。
- `detect_pdf` 返回 `is_complex_layout`；extract 返回 `is_complex`。summary 只取 detect 的 `is_complex_layout`。
- `PagesExtractionResult` **无 `page_count`**：页清单校验以 `detect_pdf().page_count` 为基准。

---

# Task 4：实现 PdfInspectorAdapter

新建：

```text
src/docchunk/adapters/pdf_inspector.py
```

职责严格限定为：

```text
调用 pdf-inspector
↓
转换外部 API
↓
生成 DocChunk 内部 page inventory
```

不允许在这里调用 MinerU。

主接口：

```python
class PdfInspectorAdapter:

    def inspect_and_extract(
        self,
        path: Path,
    ) -> PdfInspectorBundle:
        ...
```

第一步：

```python
pdf_inspector.detect_pdf(...)
```

保存：

```text
pdf_type
pdf_type_confidence
page_count
has_encoding_issues
is_complex_layout
pages_with_tables
pages_with_columns
```

第二步：

```python
pdf_inspector.extract_pages_markdown(...)
```

实际读取所有页面。

每页标准化成：

```python
NativePageResult(
    page_idx=...,
    markdown=...,
    needs_ocr=...,
    ocr_reasons=[...],
)
```

### 一个重要恢复机制

如果：

```python
extract_pages_markdown(path)
```

整份调用失败：

不要立即：

```text
整份 → MinerU
```

因为可能只是某一页异常。

改为逐页重试：

```python
for page_idx in range(page_count):
    extract_pages_markdown(
        path,
        pages=[page_idx],
    )
```

成功页面继续保留 native。

只有失败页面生成：

```python
NativePageResult(
    page_idx=N,
    markdown="",
    needs_ocr=True,
    ocr_reasons=[
        "native_extraction_failed"
    ],
    extraction_failed=True,
)
```

然后后续只把这一页交给 MinerU。

这非常符合我们的准确性原则：

> 不能因为第 20 页 native parser 异常，就让另外 99 个本来正确的电子文字页面全部重新识别。

---

# Task 5：扩展 MinerUAdapter 单页能力

现在：

```python
MinerUAdapter.prepare(path)
```

保留。

新增：

```python
MinerUAdapter.prepare_page(
    path,
    page_idx,
)
```

底层 `_run_mineru()` 改成：

```python
def _run_mineru(
    self,
    path: Path,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> Path:
```

单页调用：

```text
mineru
-p original.pdf
-o TEMP
-b hybrid-engine
--effort medium
--start 37
--end 37
```

这里：

```text
37 = 原 PDF 的 page_idx
```

也就是用户看到的：

```text
第 38 页
```

### 不物理拆 PDF

不要：

```text
原 PDF
↓
拆出 page-38.pdf
↓
MinerU
```

直接：

```text
原 PDF
↓
MinerU --start 37 --end 37
```

这样：

- 原文件不修改；
- 不增加 PDF 拆分依赖；
- provenance 更清楚；
- 临时文件更少。

### MinerU 自己返回什么 page_idx 不重要

即使 MinerU 对单页输出：

```text
page_idx = 0
```

DocChunk 必须强制改成：

```text
page_idx = 37
```

因为：

> **原 PDF 页码才是唯一权威页码。**

---

# Task 6：实现 Page Assembler

这一步先不考虑 routing。

只解决：

```text
一堆 PageFragment
↓
如何严格按原 PDF 顺序
↓
变成一个 NormalizedDocument
```

例如：

```text
Page 0 → MinerU
Page 1 → MinerU
Page 2 → pdf-inspector
Page 3 → pdf-inspector
```

输入：

```python
PageFragment(...)
```

输出：

```python
NormalizedDocument(...)
```

### 合并规则

页面之间：

```text
\n\n
```

连接。

禁止添加：

```text
--- Page 1 ---
# PAGE 1
<!-- page 1 -->
```

因为这些内容不是原文。

---

## 每页建立一个 page-level NormalizedBlock

最终 Smart PDF 不需要混用：

```text
MinerU 细 block
pdf-inspector page block
```

统一：

> **每个 PDF 页面建立一个 Page-Level Block。**

例如：

```python
NormalizedBlock(
    block_index=10,
    char_start=12345,
    char_end=15678,
    text="第11页全部 Markdown",
    page_idx=10,
)
```

这样 provenance 最稳定。

当前 DocChunk 下游真正需要的是：

```text
这个 chunk 落在哪些页
```

而不是 MinerU 内部的每个 bbox。

MinerU 现有完整 adapter 的细粒度 blocks 仍然保留，用于：

```text
MinerUAdapter.prepare()
```

Smart PDF 路径只是最终统一到 page block。

---

## Blank Page

例如：

```text
Page 1 正文
Page 2 空白
Page 3 正文
```

Page 2 即使：

```text
markdown = ""
```

也必须存在一个：

```python
PageFragment(page_idx=1)
```

只是不产生正文 block。

这样 Page 3 仍然是：

```text
page_idx = 2
page_number = 3
```

不能因为空白页而变成“第 2 页”。

---

# Task 7：实现 SmartPdfAdapter

这是核心 orchestration。

新建：

```text
src/docchunk/adapters/pdf.py
```

最终：

```python
class SmartPdfAdapter(DocumentAdapter):

    def prepare(
        self,
        path: Path,
    ) -> NormalizedDocument:
        ...
```

核心逻辑：

```python
bundle = inspector.inspect_and_extract(path)

for page in bundle.pages:

    if page.needs_ocr:

        mineru_result = mineru.prepare_page(
            path,
            page.page_idx,
        )

        parser = "mineru"

    else:

        markdown = page.markdown

        parser = "pdf_inspector"
```

然后：

```text
PageFragment[]
↓
Page Assembler
↓
NormalizedDocument
```

---

# 路由决策规则

先于逐页循环执行**方案 A 整份捷径**：

```python
if all(page.needs_ocr for page in bundle.pages):
    # 纯扫描 PDF：整份一次 MinerU 调用（含 extraction_failed 页）
    return self._prepare_whole_mineru(
        path, parser_route="mineru_only",
    )
```

要求：

- `MinerUAdapter.prepare()` 只调用一次；
- `prepare_page()` 一次都不调用；
- metadata 记录 `parser_route = mineru_only`、`routing.policy = page_smart_v1`；
- `page-routing.jsonl` 仍每页一行 `parser=mineru`，`route_reason` 取该页原始原因（如 `needs_ocr`）；
- 整份调用失败 → prepare FAILED，禁止降级。

否则进入逐页循环，核心条件只有一个：

```python
if page.needs_ocr:
    MinerU
else:
    pdf-inspector
```

不要添加：

```python
if confidence < 0.8:
```

也不要添加：

```python
if table:
```

或者：

```python
if columns:
```

---

# Encoding Issue

如果：

```text
has_encoding_issues = true
```

并且 pdf-inspector 能定位：

```text
Page 32
suspected_garbled_text
```

那么：

```text
Page 32 → MinerU
```

其他页继续 native。

但是如果：

```text
has_encoding_issues = true
```

却不知道到底哪一页存在问题：

```text
没有 OCR page
没有 page-specific reason
```

则：

```text
整份 PDF → MinerU
```

原因：

```text
unlocalized_encoding_issue
```

这是准确率优先情况下必要的保守 fallback。

---

# pdf-inspector 整体失败

例如：

```text
无法打开 PDF
无法取得 page_count
page inventory 异常
```

这时候已经没有可靠条件进行页级路由。

因此：

```text
Whole PDF
↓
MinerUAdapter.prepare()
```

记录：

```text
parser_route =
full_mineru_fallback

reason =
pdf_inspector_failed
```

---

# Page Inventory 不一致

例如：

```text
detect_pdf:
100 页

extract_pages_markdown:
99 页
```

禁止：

```text
猜缺的是哪一页
```

直接：

```text
整份 → MinerU
```

记录：

```text
page_inventory_mismatch
```

---

# MinerU OCR 页失败

例如：

```text
Page 2
needs_ocr = true
```

然后：

```text
MinerU Page 2
→ ERROR
```

此时：

```text
整个 prepare = FAILED
```

绝对不能：

```text
“那就用 pdf-inspector 原来的结果吧”
```

因为我们已经知道：

```text
该页 native 内容不可靠
```

宁可失败，也不能静默产生错误 Corpus。

---

# Task 8：正式替换 PDF 默认 Adapter

当前：

```python
if suffix == ".pdf":
    return MinerUAdapter(...)
```

修改为：

```python
if suffix == ".pdf":
    return SmartPdfAdapter(...)
```

从这一刻开始：

```text
所有 PDF
↓
SmartPdfAdapter
```

---

# Normalization Fingerprint 必须升级

旧版：

```text
PDF → MinerU
```

新版：

```text
PDF
→ pdf-inspector
→ Page Routing
→ MinerU/native
```

生成的 normalized Markdown 很可能不同。

所以旧缓存必须自动失效。

定义：

```python
PAGE_SMART_PDF_POLICY_VERSION = (
    "page_smart_v1"
)
```

fingerprint 至少加入：

```text
pdf_adapter:
page_smart_v1

pdf_inspector_version

mineru_command

mineru_backend

mineru_effort
```

这样未来改变路由算法：

```text
page_smart_v1
↓
page_smart_v2
```

就能自然触发 normalization rebuild。

---

# Task 9：升级 `docchunk inspect`

以后：

```bash
docchunk inspect report.pdf
```

不应该只是告诉用户：

```text
PDF 需要转换
```

而应该真正做：

```text
PDF Full Preflight
```

但：

> **inspect 不调用 MinerU。**

例如：

```text
PDF Inspection

file:
审计报告.pdf

type:
mixed

pages:
100

planned native:
97

planned MinerU:
3

OCR pages:
1-3

tables:
5, 7, 20

columns:
none

encoding issues:
false

policy:
page_smart_v1
```

这样真正 split 前就知道：

```text
哪些页面准备 OCR。
```

如果 OCR 页很多：

```text
1,2,3,21,84,85
```

CLI 显示成：

```text
1-3, 21, 84-85
```

---

# Task 10：Doctor

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

这里只检查：

```text
package installed
import working
version
```

不检查 pdf-inspector OCR runtime。

因为我们根本不用它的 OCR。

---

# Task 11：端到端 Pipeline 测试

必须模拟几个关键场景。

## A. Pure Native

```text
10 pages
全部 pdf-inspector
```

断言：

```text
MinerU calls = 0
parser_route = native_only
```

---

## B. Pure Scanned

```text
10 pages
全部 needs_ocr
```

断言（方案 A）：

```text
MinerU prepare() 整份调用 = 1
MinerU prepare_page = 0
parser_route = mineru_only
page-routing.jsonl = 10 行，每行 parser=mineru
```

---

## C. 典型审计报告

最重要。

例如：

```text
100 页

1-3 页：
签章扫描页

4-100 页：
电子财务报告
```

必须：

```text
MinerU = 3 pages
pdf-inspector = 97 pages
```

而不是：

```text
MinerU = 100 pages
```

---

## D. 中间扫描附件

```text
1-20 native
21 scanned
22-50 native
```

必须只有：

```text
Page 21 → MinerU
```

---

## E. Blank Page

```text
1 native
2 blank
3 native
```

最终 Page 3 仍然：

```text
page_number = 3
```

---

## F. Table

```text
table = true
needs_ocr = false
```

必须：

```text
pdf-inspector
```

---

## G. Columns

```text
columns = true
needs_ocr = false
```

必须：

```text
pdf-inspector
```

---

## H. Native Extraction Failure

如果：

```text
Page 18
native extraction exception
```

只：

```text
Page 18 → MinerU
```

---

## I. MinerU Failure

如果：

```text
Page 3 requires OCR
MinerU fails
```

整个：

```text
prepare FAILED
```

---

# Task 12：真实外部工具测试

普通 CI 不要依赖 MinerU。

额外建立：

```text
tests/test_pdf_external.py
```

标记：

```python
pytest.mark.external
```

实际验证：

### Native PDF

```text
native page
→ pdf-inspector
→ MinerU 0 次
```

### Scanned PDF

```text
scan
→ MinerU
```

### Mixed PDF

最好自己生成一个：

```text
Page 1 native
Page 2 scan
Page 3 native
```

最终：

```text
pdf-inspector = 2
MinerU = 1
```

---

# Task 13：README 与版本号

版本：

```text
1.0.3
↓
1.1.0
```

README 明确说明：

```text
Native PDF page
→ pdf-inspector

OCR-required PDF page
→ MinerU

Mixed PDF
→ page-level merge
```

并写典型：

```text
100 页审计报告

1-3 签章扫描
4-100 电子文本

=>

1-3 MinerU
4-100 pdf-inspector
```

---

# Task 14：最终验收

依次执行：

```bash
uv run pytest -q
```

然后：

```bash
uv run ruff check .
```

然后：

```bash
uv run mypy src/docchunk
```

然后：

```bash
uv run docchunk doctor
```

交付收尾（用户已授权：完成后推送 GitHub 并补充 README）：

```bash
git log --oneline main..HEAD        # 逐 Task commit 审查
git switch main && git merge --no-ff feat/page-level-smart-pdf-routing
git tag -a v1.1.0 -m "docchunk v1.1.0: page-level smart pdf routing"
git push origin main --follow-tags
```

推送前确认：无真实审计资料、无 OCR 中间图片、无模型文件、无临时产物进入 Git。

---

# 最重要的真实资料验收

选择一份真实 Mixed PDF 审计报告：

```bash
uv run docchunk inspect \
  /path/to/audit-report.pdf
```

首先确认：

```text
OCR pages
```

符合实际情况。

例如：

```text
1-3
```

然后：

```bash
uv run docchunk split \
  /path/to/audit-report.pdf \
  --force \
  --verbose
```

最终必须存在：

```text
source/documents/D0001/

normalized.md
blocks.jsonl
source-ref.json
page-routing.jsonl
```

然后：

```bash
uv run docchunk verify \
  /path/to/corpus
```

必须：

```text
PASS
```

---

# 人工准确性抽查

这一步不能省。

至少抽：

```text
1 个扫描签章页
1 个普通正文页
2 个数字密集财务报表页
1 个财务报表附注表格页
1 个跨页段落附近页面
```

逐项检查：

```text
数字
小数点
负号
百分号
中文
表格内容
页码
```

是否与原 PDF 一致。

如果真实测试中发现：

```text
pdf-inspector:
needs_ocr = false
```

但实际上某些数字被漏掉，

不要马上添加：

```text
confidence < 0.8
```

这种没有依据的规则。

正确处理方式是：

```text
保留这个失败案例
↓
建立回归测试
↓
分析具体失败模式
↓
针对失败模式增加质量 guard
```

---

# page-routing.jsonl

这是整个 Smart PDF Routing 的逐页审计证据。

例如：

```json
{"page_idx":0,"page_number":1,"parser":"mineru","route_reason":"needs_ocr","needs_ocr":true,"ocr_reasons":["scanned"]}
{"page_idx":1,"page_number":2,"parser":"mineru","route_reason":"needs_ocr","needs_ocr":true,"ocr_reasons":["scanned"]}
{"page_idx":2,"page_number":3,"parser":"pdf_inspector","route_reason":"native_text_safe","needs_ocr":false,"ocr_reasons":[]}
```

必须满足：

```text
一页 = 一行

page_idx 唯一

page_idx 连续

page_idx 从 0 开始

page_number = page_idx + 1
```

---

# source-ref.json

不要保存全部逐页 route。

只保存 summary：

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
    "page_routing_sidecar":
      "page-routing.jsonl"
  }
}
```

---

# 最终 Failure Matrix

| 场景 | 最终行为 |
|---|---|
| 全部页 needs_ocr（纯扫描） | 整份单次 MinerU（方案 A，`mineru_only`） |
| Native page 正常 | pdf-inspector |
| `needs_ocr=true` | MinerU 单页 |
| Native extraction 单页失败 | MinerU 单页 |
| Encoding issue 能定位页面 | 对应页 MinerU |
| Encoding issue 无法定位 | 整份 MinerU |
| pdf-inspector 整体失败 | 整份 MinerU |
| Page inventory 不一致 | 整份 MinerU |
| MinerU OCR 页失败 | prepare FAILED |
| 空白 native page | 保留页号，不产生正文 block |
| Table + native safe | pdf-inspector |
| Columns + native safe | pdf-inspector |
| confidence 高或低 | 不单独影响路由 |

---

# Definition of Done

最终只有以下条件全部满足，才算完成：

- `.pdf` 已默认进入 `SmartPdfAdapter`。
- `pdf-inspector` 已成为正式依赖。
- 纯扫描 PDF 由整份单次 MinerU 调用完成（方案 A），page-routing.jsonl 仍每页一行。
- 没有调用 pdf-inspector 自带 OCR。
- Native-safe 页面不调用 MinerU。
- OCR-required 页面只调用对应页 MinerU。
- Mixed PDF 能真正混合两种 parser。
- Confidence 不参与 threshold 判断。
- 表格不自动 MinerU。
- 多栏不自动 MinerU。
- 内部页码全部 0-based。
- 用户页码全部 1-based。
- 空白页不会导致页码漂移。
- `page-routing.jsonl` 每页恰好一行。
- `source-ref.json` 不复制完整逐页 routing。
- Atomic `page_start/page_end` 正确。
- pdf-inspector 整体异常能够整份 fallback。
- 已知 OCR 页 MinerU 失败会阻止错误结果继续生成。
- normalization fingerprint 已升级为 `page_smart_v1`。
- `docchunk inspect` 能预告 OCR 页面。
- `docchunk doctor` 能检查 pdf-inspector。
- 原测试全部通过。
- 新测试全部通过。
- Ruff 通过。
- Mypy 通过。
- 至少完成一份真实 Mixed PDF 审计报告人工抽查。
- 项目版本升级为 `1.1.0`。
- Git 中不存在真实审计资料、OCR 中间图片、模型文件或临时产物。