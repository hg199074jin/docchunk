# docchunk

Lossless, token-aware long-document preprocessing for reliable LLM reading.

`docchunk` 把书籍、课程逐字稿、PDF、Word、Markdown 切成**可验证、可恢复、可追溯**的阅读单元（Atomic Chunk 与 Reading Batch），让任何大模型都能分批高质量地读完一份长资料——而不是"塞进上下文"。

> **Chunking is lossless. Distillation may be lossy.**
> 切片尽可能无损：Atomic 正文重新拼接后与标准化原文逐字符等价；`docchunk verify` 负责证明这一点。

## 为什么不是简单按字符切

- 按固定字符数切割会打断句子、表格和标题结构，下游模型丢失论证链条；
- `docchunk` 沿**自然语言边界**（标题 → 段落 → 句子 → 子句）按 token 预算切分，超长表格跨片时携带表头上下文（明确标记为提示，不污染原文）；
- 两级结构：**Atomic Chunk**（约 6K tokens，稳定、无重叠、可复用）与 **Reading Batch**（约 24K tokens，按模型预算临时组合，相邻 Batch 复叠 1 个完整 Atomic 作上下文桥）；
- 换模型只需 `rebuild-batches`，不必重新 OCR/转换/切分；
- 一切都可验证：`verify` 能发现任何缺口、重复、篡改。

## 安装

需要 Python 3.12 与 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/hg199074jin/docchunk.git
cd docchunk
uv sync
uv run docchunk doctor
```

> 正式发布 PyPI 之前不提供 `pip install docchunk`。

外部工具：

- **Pandoc**（DOCX 支持）：`brew install pandoc`
- **MinerU**（PDF 支持）：见 [MinerU 安装文档](https://github.com/opendatalab/MinerU)。`docchunk` 会自动按 `PATH → ~/.venvs/mineru/bin/mineru` 解析可执行文件；也可以在配置中写绝对路径。

## doctor：先体检

```bash
uv run docchunk doctor
```

检查 Python 版本、Pandoc、MinerU（显示解析后的路径与版本）、tiktoken 词表加载、Corpus 根目录可写性。全部 OK 时输出 PASS 语义（exit 0）。

## 快速上手：TXT/Markdown

```bash
echo "第一段。第二段。第三段。" > demo.txt
uv run docchunk split demo.txt
```

输出类似：

```text
/Volumes/ORICO/LongDocCorpus/demo-3f786850e387
```

然后：

```bash
uv run docchunk status "/实际输出的Corpus路径"
uv run docchunk verify "/实际输出的Corpus路径"   # PASS
```

## DOCX 示例

```bash
uv run docchunk split "$HOME/Documents/report.docx"
```

默认走 Pandoc 转 GFM Markdown。Pandoc 失败会显式报错；只有显式开启 `docx_fallback_to_mineru` 才会降级，且降级会被记录在 Manifest 中。

## PDF 示例（MinerU）

先确认环境（`docchunk` 会自动解析 MinerU 路径，`doctor` 可查看解析结果）：

```bash
uv run docchunk doctor
```

再运行：

```bash
uv run docchunk split "$HOME/Documents/book.pdf"
```

PDF 默认走 MinerU（本机默认 `-b hybrid-engine --effort medium`），产出 Markdown 的同时保留 `content_list` 页码溯源——每个 Atomic 都能回查到原 PDF 页码。

## 整个课程文件夹示例

```bash
uv run docchunk split "$HOME/Documents/课程"
```

```text
课程/
├── 1-第一课.md
├── 2-第二课.md
└── 10-第十课.md
```

目录按**自然排序**（1、2、10）作为一个 Document Set 处理，每个文件保留独立 `document_id` 与来源身份，绝不粗暴拼接成无来源长文本。

## 输出目录解释

```text
<corpus-root>/<corpus-id>/
├── manifest.json        # 权威元数据（策略、指纹、验证状态）
├── index.jsonl          # Atomic 权威索引（token 数/字符区间/标题路径/页码）
├── state.json           # 处理状态机
├── combined.md          # 派生阅读视图
├── source/              # normalized 原文 + blocks + source-ref
├── atomic/Axxxxxx.md    # 最小阅读单元（frontmatter + 原样正文）
└── batches/Bxxxx.md     # 模型实际阅读的窗口（含 Context Bridge 标记）
```

## verify：完整性校验

```bash
uv run docchunk verify <corpus-path>
```

按文档重建原文逐字符比对、核对 token 数、检查 Atomic 无缺口/无重复、Batch 新材料恰好覆盖全部 Atomic 一次、overlap 策略正确、PDF 页码存在性。`docchunk split` 完成后会自动 verify，失败 exit 1。

## rebuild-batches：换模型不改原文

```bash
uv run docchunk rebuild-batches <corpus-path> \
  --target-tokens 32000 \
  --soft-min-tokens 20000 \
  --soft-max-tokens 40000 \
  --overlap-atomic-count 1
```

只重建阅读窗口，Atomic 文件哈希完全不变——这就是两级架构的收益。

## 怎么交给 Codex / Agent

```text
请阅读这个 Corpus 的 batches 目录（按 B0001 顺序）：
<corpus-path>/batches/
每个文件的 frontmatter 区分了 overlap_atomic_ids（上下文）与 new_atomic_ids（新材料）；
来源回查用 index.jsonl。
```

## 怎么交给 Cangjie / Nuwa

安装 `skills/longdoc-router/SKILL.md` 为 Agent Skill 后，对 Agent 说：

```text
请用 longdoc-router 处理这个 Corpus：<corpus-path>
这是课程逐字稿，目标是调用 cangjie-skill 蒸馏。
完成后交给 personal-capability-distiller 做个人能力沉淀。
```

Router 会校验 Corpus → 按 Batch 调度 → 维护断点 → 交给下游 Skill，且不修改任何第三方 Skill。

## 常见错误

| 症状 | 原因 | 怎么办 |
|---|---|---|
| `Pandoc executable was not found` | 没装或 PATH 不对 | `brew install pandoc` |
| `MinerU executable was not found` | MinerU 不在 PATH 且 venv 回退也失败 | `uv run docchunk doctor`；或在配置中写可执行文件绝对路径 |
| verify missing atomic | Corpus 被人为移动/删除 | 保留原 Corpus，重新 `split --force` 或修复损坏文件 |
| forced split 很多 | OCR 无标点/超大表格 | 检查 MinerU 输出质量（`docchunk inspect` 也会给 warning） |
| 第二次 split 没重新 OCR | 正常幂等复用 | source hash 未变化；确要重跑加 `--force` |
| 改 24K 为 32K | 不需要重新切 Atomic | `rebuild-batches` |

## 升级与卸载

```bash
cd docchunk && git pull && uv sync     # 升级
rm -rf docchunk                        # 卸载代码
rm -rf <你的 corpus-root>              # 删除生成的 Corpus（默认 /Volumes/ORICO/LongDocCorpus）
```

## 隐私说明

- `docchunk` 本身**不调用任何 LLM API**，不上传用户资料；
- 全部处理在本地完成（MinerU/Pandoc/tiktoken 词表均为本地推理或静态资源）；
- 若你的 MinerU 配置了云端后端，那是 MinerU 环境自身的配置，`docchunk doctor` 会显示但不会替你启用；
- 原始文件永不修改，所有产物写入 Corpus 目录。

## 设计文档

- [设计稿](docs/superpowers/specs/2026-08-29-docchunk-longdoc-router-design.md)
- [实施计划](docs/superpowers/plans/2026-08-29-docchunk-longdoc-router-v1.md)

## License

[MIT](LICENSE)
