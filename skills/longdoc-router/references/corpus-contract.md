# Corpus 数据契约

docchunk 生成的 Corpus 是 longdoc-router 与所有下游 Skill 之间的权威数据接口。

## 目录结构

```text
<corpus-root>/<corpus-id>/
├── manifest.json        # 权威入口
├── index.jsonl          # Atomic 权威索引（每行一个 Atomic）
├── state.json           # 处理状态机
├── combined.md          # 派生阅读视图（不参与无损重建判断）
├── source/
│   ├── normalized.md    # 单文件时的一致入口
│   └── documents/Dxxxx/ # normalized.md / blocks.jsonl / source-ref.json
├── atomic/Axxxxxx.md    # frontmatter + 原样正文
├── batches/Bxxxx.md     # 模型实际阅读的文件
└── runs/                # downstream run 状态
```

## 权威关系

```text
manifest.json       ← 元数据、策略、指纹、验证状态的权威入口
index.jsonl         ← Atomic 元数据与来源位置的权威索引
atomic/*.md 正文    ← 原文本身（与 normalized.md 逐字符等价）
batches/Bxxxx.md    ← 给模型阅读的唯一入口
source/normalized.md ← 只用于校验和回查，不得让下游重新切分
combined.md         ← 便利视图，明确标记为派生物
```

## 阅读规则

1. 下游按 `batches/B0001.md → B0002.md → ...` 顺序阅读。
2. 每个 Batch 的 frontmatter 区分 `overlap_atomic_ids`（Context Bridge，上下文专用）与
   `new_atomic_ids`（新材料）。overlap 只能用于维持连续性，不得当作新证据重复提取。
3. Batch 内若出现 `Synthetic Table Context`，它是帮助理解跨 Atomic 表格的上下文提示，
   **不是新的原文**。
4. 需要回查原文时：用 Atomic id 查 `index.jsonl`，得到 char_start/char_end、heading_path、
   source file 与 PDF 页码（page_start/page_end，1-based）。
5. 禁止对 `source/normalized.md` 自行重新分块——那是 docchunk 的职责。

## 校验门

任何下游处理开始前必须满足：

```bash
docchunk verify <corpus-path>   # 输出 PASS
```

verify 检查：Atomic 无缺口/无重复/顺序单调、token 数一致、normalized 可逐字符重建、
Batch 新材料恰好覆盖全部 Atomic 一次、overlap 策略正确、PDF 页码存在性。
