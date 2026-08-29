# docchunk Launch Kit

这份文档用于发布、介绍和传播 `docchunk`。核心原则：不要把它介绍成“又一个 chunker”，而要强调它解决的是 **让 AI Agent 可验证地读完整份长资料**。

GitHub: https://github.com/hg199074jin/docchunk

---

## 1. 一句话定位

### 中文

**docchunk：让 AI Agent 可靠读完整本书、整套课程和长文档的无损预处理层。**

短版：

> 让 AI Agent 读长文档，而不是把长文档塞进上下文。

### English

**docchunk — Lossless, verifiable long-document preprocessing for AI agents.**

Alternative:

> Make long documents reliably readable by AI agents.

---

## 2. 核心记忆点

统一使用以下主张，避免每个平台换一套定位：

1. **Lossless** — Atomic 正文可重新拼接，并与标准化原文逐字符验证；
2. **Verifiable** — `docchunk verify` 检查缺口、重复、篡改和 Batch 覆盖；
3. **Token-aware** — 沿自然语言边界按 token 预算切，而不是固定字符数；
4. **Model-independent Atomic layer** — 换模型只重建 Reading Batch，不重新 OCR / 切 Atomic；
5. **Agent-ready** — Corpus、Batch、来源索引和 `longdoc-router` 都围绕 Agent 完整阅读设计；
6. **Local-first** — `docchunk` 本身不调用 LLM API，不主动上传文档。

品牌句：

> **Chunking is lossless. Distillation may be lossy.**

---

## 3. 不要怎么介绍

不推荐：

> 我做了一个 PDF / Word 文档切片工具。

不推荐：

> 一个 semantic chunker / RAG chunker。

这会直接掉进高度拥挤的 RAG chunking 类别。

推荐：

> 我发现让 Agent “读一本书”和把文本切成 RAG chunks，其实是两个不同的问题。于是我做了 docchunk：先建立一个无损、可验证的 Atomic 文档层，再按模型上下文临时组合成 Reading Batches。这样可以检查 Agent 是否真正覆盖了全部材料，而且换模型不用重新 OCR 和切原文。

---

## 4. 60–90 秒 Demo 脚本

Demo 不需要讲代码架构。只证明一件事：**一本长文档可以变成 Agent 可控、可验证的完整阅读任务。**

### 镜头 1：问题（0–10 秒）

画面：一个 200–500 页 PDF。

字幕：

> “把 300 页 PDF 扔进 200K context，就等于 AI 真正读完了吗？”

### 镜头 2：运行（10–25 秒）

```bash
uv run docchunk doctor
uv run docchunk split "book.pdf"
```

展示 Corpus 输出路径。

### 镜头 3：结构（25–40 秒）

快速打开：

```text
manifest.json
index.jsonl
atomic/
batches/
```

字幕：

> Atomic = 稳定事实层  
> Batch = Agent 阅读窗口

### 镜头 4：验证（40–55 秒）

```bash
uv run docchunk verify <corpus-path>
```

突出 PASS。

字幕：

> “不是相信它没漏，而是验证它没漏。”

### 镜头 5：交给 Agent（55–75 秒）

把以下提示交给 Codex / Claude Code：

```text
请按 B0001、B0002……顺序阅读 batches。
把 overlap_atomic_ids 只作为上下文，new_atomic_ids 视为新材料。
完成全部 Batch 后再进行跨文档总结。
```

### 镜头 6：收尾（75–90 秒）

字幕：

> Chunking is lossless. Distillation may be lossy.
>
> github.com/hg199074jin/docchunk

---

## 5. V2EX「分享创造」首发稿

### 标题

**[分享创造] docchunk：我做了一个让 AI Agent 可验证地读完整本书/长 PDF 的开源工具**

### 正文

最近在折腾一个问题：怎么让 Codex / Claude Code / Agent 真正“读完”一本书或一整套课程，而不是把几十万 token 一股脑塞进上下文，然后默认模型已经完整处理了。

我发现传统 RAG chunker 和这个需求其实不完全一样。RAG 更关注“怎么切方便检索”，但 Agent 连续阅读更关心另外几件事：

- 全文到底有没有覆盖；
- 有没有因为切片产生缺口或重复；
- 上下文窗口换了以后，是否要重新 OCR / 重切；
- 一个结论能不能回查到原文甚至 PDF 页码；
- Agent 中断以后能不能继续按批次读。

所以做了 `docchunk`。

它把长资料分成两层：

- **Atomic Chunk**：稳定、无重叠、可复用的事实层；
- **Reading Batch**：根据模型 token budget 临时组合的阅读窗口，相邻 Batch 用完整 Atomic 做 Context Bridge。

最核心的是 `verify`：会把 Atomic 正文重新拼回来和标准化原文逐字符比对，并检查缺口、重复、Batch 覆盖、token 数、来源引用和 PDF 页码。

因此我的设计原则是：

> **Chunking is lossless. Distillation may be lossy.**

目前支持：

- TXT / Markdown 直接处理；
- DOCX → Pandoc；
- PDF → MinerU，并保留页码来源；
- 整个课程文件夹作为一个 Document Set；
- `rebuild-batches`：换模型窗口不重新切 Atomic；
- `longdoc-router`：让 Agent 按 Batch 调度下游 Skill。

项目刚开源，当前更希望得到真实长文档场景的反馈，尤其是复杂 PDF、表格、OCR、课程逐字稿以及 Agent workflow 的边界案例。

GitHub：
https://github.com/hg199074jin/docchunk

如果你正好也在做 Agent 长文档阅读 / 知识蒸馏 / RAG 前处理，很欢迎试一下，也欢迎直接挑设计上的问题。

---

## 6. Linux.do 首发稿

### 标题

**开源了 docchunk：给 Codex / Claude Code / Agent 用的“长文档完整阅读层”，支持 verify 检查有没有漏读材料**

### 正文

最近自己需要让 Agent 连续处理整本书、课程逐字稿和长 PDF，于是做了一个本地工具 `docchunk`。

我最开始也想直接用普通 semantic chunking，但后来发现目标不一样：

RAG 的问题通常是“用户问一句话时应该召回哪几块”；而我的问题是“Agent 要把所有材料按顺序真正读一遍，怎么证明没有漏、没有重复，而且随时能回查来源”。

所以最后做成了两级结构：

```text
Document
  ↓
Normalized Source
  ↓
Atomic Chunks     ← 稳定、无重叠
  ↓
Reading Batches   ← 按具体模型 token budget 临时组合
  ↓
Agent / Skill
```

比较特别的地方：

- `verify` 可以逐字符重建标准化原文；
- Batch 会区分 overlap 和 new material，因此可以验证新材料正好覆盖所有 Atomic 一次；
- PDF 走 MinerU 并保留页码 provenance；
- 换模型只需要 `rebuild-batches`；
- 一个课程文件夹可以直接作为 Document Set，文件各自保持来源身份；
- 本身不调用 LLM API，适合本地敏感材料前处理；
- 仓库里带 `longdoc-router` Skill，可以负责按 Batch 调度其他蒸馏 Skill。

一句话原则：

> **Chunking is lossless. Distillation may be lossy.**

GitHub：
https://github.com/hg199074jin/docchunk

目前刚进入公开使用阶段。如果大家手里正好有“特别难切”的 PDF、表格、OCR 文档或者整套课程，欢迎拿来测试；能给我一个可复现的边界案例，比单纯 Star 对项目更有帮助。

---

## 7. 知乎 / 公众号长文标题池

优先用问题驱动标题，不要直接从项目名开始：

1. **我发现 AI 根本没有“读完”那本 300 页的书，于是我做了 docchunk**
2. **200K 上下文，为什么仍然解决不了“让 AI 可靠读完整本书”？**
3. **RAG 会切文档，但我想让 Agent 真正读完整份材料**
4. **如何证明 AI 没有漏读你的长文档？我做了一个 verify 层**
5. **从“把 PDF 塞给 AI”到“让 Agent 可验证地读完 PDF”**

推荐文章结构：

```text
1. 我遇到的真实问题
2. 为什么超长 context 不是完整答案
3. 为什么传统 RAG chunking 也不是同一个问题
4. Atomic + Reading Batch 的设计
5. verify 为什么是核心
6. 一个真实长 PDF Demo
7. 怎么接 Codex / Claude Code / Skill
8. GitHub + 邀请真实案例
```

---

## 8. 小红书短内容

### 标题

**我做了个工具，让 AI 真正“读完”一本 300 页的书**

### 正文

我最近一直在折腾一个问题：

把一本几百页的 PDF 丢给 AI，真的等于它“读完”了吗？

我最后发现，长上下文 ≠ 可验证的完整阅读。

所以自己开源了一个工具：**docchunk**。

它不是普通的 RAG 切片器，而是先把整份资料变成一个稳定的 Atomic 文档层，再按照不同 AI 的上下文窗口组合成 Reading Batch。

最关键的是：

**它可以 verify。**

也就是说，不是“我觉得应该没漏”，而是可以检查：

- 原文有没有缺失；
- 有没有重复；
- 每一个 Batch 到底读了哪些新材料；
- PDF 内容来自哪一页；
- 换 Claude / GPT / 其他模型时，能不能不重新处理原文。

我的设计原则只有一句：

> Chunking is lossless. Distillation may be lossy.

现在已经开源：

https://github.com/hg199074jin/docchunk

如果你也经常让 AI 读书、读课程、读长 PDF，可以拿真实资料试一下。

---

## 9. Show HN

### Title

**Show HN: docchunk – Lossless, verifiable long-document preprocessing for AI agents**

### Body

Hi HN,

I built `docchunk` because I wanted coding agents to read entire books, course transcripts, and long PDFs without treating “fits in the context window” as proof that all material was actually processed.

Most chunking libraries I found are primarily designed for retrieval. `docchunk` targets sequential, exhaustive agent reading instead.

It uses two layers:

- **Atomic Chunks**: stable, non-overlapping units derived from natural language boundaries;
- **Reading Batches**: model-specific windows composed from Atomic Chunks, with a whole-Atomic context bridge between adjacent batches.

The part I care about most is verification. `docchunk verify` reconstructs normalized source text and checks it character-by-character, validates Atomic coverage, token counts, Reading Batch coverage/overlap, source references, and PDF page provenance.

That also means changing model context size doesn't require OCR or re-chunking the source: you can rebuild only the Reading Batches.

Current inputs include Markdown/TXT, DOCX via Pandoc, PDFs via MinerU, and ordered multi-file document sets such as a course directory.

The tool itself is local-first and does not call an LLM API.

The design principle is:

> **Chunking is lossless. Distillation may be lossy.**

Repo: https://github.com/hg199074jin/docchunk

I'd especially appreciate feedback from people working on long-running coding agents, document agents, knowledge distillation, or difficult PDF pipelines. Real failure cases are very welcome.

---

## 10. Reddit 版本

推荐社区要先阅读各 subreddit 当日规则，不做重复刷屏。

### Title

**I built an open-source preprocessing layer to verify that AI agents actually cover an entire long document**

### Body

I've been experimenting with agents reading books and long course transcripts, and I kept running into a distinction that retrieval-oriented chunking doesn't fully address: I don't just want good chunks to retrieve later — I want an agent to sequentially consume *all* of the material and be able to verify that nothing was skipped or duplicated.

I built `docchunk` around that use case.

It creates stable, non-overlapping Atomic Chunks, then composes model-specific Reading Batches. A verifier reconstructs the normalized source character-by-character and validates coverage, overlap, token counts and provenance. PDFs parsed with MinerU can also retain page references.

If I switch to a model with a different context budget, I rebuild the batches without re-running OCR or changing the Atomic layer.

It's local-first and doesn't call an LLM API itself.

Repo: https://github.com/hg199074jin/docchunk

I'm mainly looking for real-world edge cases right now, especially ugly PDFs, tables, OCR output, and long-running agent workflows.

---

## 11. X / Twitter

### English

I open-sourced `docchunk` — a lossless, verifiable preprocessing layer for AI agents that need to read *entire* long documents.

Not RAG-first chunking:
→ stable Atomic Chunks
→ token-aware Reading Batches
→ character-level verification
→ PDF provenance
→ rebuild batches when switching models

“Chunking is lossless. Distillation may be lossy.”

https://github.com/hg199074jin/docchunk

### 中文

开源了 `docchunk`。

它不是为了“把 PDF 切碎做 RAG”，而是解决另一个问题：**怎么让 Agent 按顺序读完整本书/课程/长文档，并验证没有漏读。**

Atomic 稳定层 + token-aware Reading Batch + `verify` + PDF 页码追溯；换模型只重建 Batch。

> Chunking is lossless. Distillation may be lossy.

https://github.com/hg199074jin/docchunk

---

## 12. 给其他开源作者的 Integration 私信

不要群发。只找确实与长文档、Agent、知识蒸馏有互补关系的项目。

### 中文

你好，我最近开源了一个长文档预处理工具 `docchunk`：
https://github.com/hg199074jin/docchunk

它主要解决 Agent / Skill 在处理整本书、整套课程时的上游读取问题：把原资料转换成可验证的 Atomic Chunks 和按 token budget 组合的 Reading Batches，并保留来源追溯。

我看了你的项目，感觉两者更像上下游关系，而不是竞争关系：`docchunk` 负责“可靠读全材料”，你的项目负责后续的 ______。

我准备写一个最小集成示例，不需要修改你现有项目。如果你觉得这个方向合理，我会按松耦合方式做，并欢迎你指出更合适的接入点。

### English

Hi — I recently open-sourced `docchunk`:
https://github.com/hg199074jin/docchunk

It focuses on the upstream side of long-document agent workflows: turning books, course transcripts and PDFs into verifiable Atomic Chunks plus token-budgeted Reading Batches with provenance.

Your project looks complementary rather than competitive: `docchunk` could handle exhaustive source reading, while your project handles ______ downstream.

I'm considering writing a minimal, loosely coupled integration example that would not require changes to your project. If that sounds useful, I'd appreciate any guidance on the cleanest integration point.

---

## 13. GitHub Repository 设置建议

### Description

```text
Lossless, verifiable, token-aware long-document preprocessing for AI agents.
```

### Topics

建议优先使用 10–15 个高相关 topic，不要堆无关关键词：

```text
llm
ai-agents
document-processing
chunking
long-context
rag
pdf
markdown
docx
mineru
codex
claude-code
knowledge-base
tokenization
python
```

### Discussions

在开始有真实用户以后开启。建议分类：

- General
- Ideas
- Show and tell
- Q&A

---

## 14. 第一阶段发布顺序

不要同一天向所有平台复制粘贴。

### Day 0 — 仓库准备

- README 产品化；
- Description + Topics；
- CONTRIBUTING；
- Demo 视频/GIF；
- 测试全绿；
- 确认一个公开、合法的 Demo 文档。

### Day 1 — 核心中文开发者

- V2EX 分享创造；
- 当天认真回复每一个技术问题；
- 收集 README 看不懂的位置。

### Day 2–3 — AI 开发者社区

- Linux.do；
- 用更偏 Agent workflow 的角度重写，不复制 V2EX 原文。

### Day 4–7 — 内容沉淀

- 知乎 / 公众号长文；
- 小红书短内容或 Demo 视频；
- 根据第一批反馈修 README 和 Issue 模板。

### 英文准备成熟后

- Show HN；
- Reddit（按社区规则）；
- X；
- Product Hunt 放在安装、Demo、文档都更成熟以后，不急于第一天提交。

---

## 15. 第一阶段不要追求的东西

不要先追：

- 10K Stars；
- 到处求 Star；
- 大量无差别私信；
- 为了宣传继续堆新功能；
- 夸张性能数字却没有 benchmark。

第一阶段真正的北极星指标：

```text
100 个相关开发者 Star
10 个真实安装
5 个真实文档运行
3 个高质量 Issue
1 个外部 PR / Integration
```

如果出现真实用户反复处理长文档，项目才算完成冷启动。
