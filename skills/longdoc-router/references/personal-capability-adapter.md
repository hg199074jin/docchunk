# personal-capability-distiller Handoff 契约

`personal-capability-distiller` 是长期知识与能力沉淀层，不是原始文档的第一遍读取器。
只有当 Cangjie/Nuwa（或直接阅读）产出蒸馏结果后，才进入本 handoff。

## handoff 内容（固定字段）

```text
distilled artifact path     # 蒸馏产物路径
source title
source type                 # book / course / interview-set / ...
raw source pointer          # 原始文件路径
raw source SHA256
corpus_id
corpus path
manifest path
downstream adapter used     # cangjie / nuwa / direct-reading
downstream output path
```

## 明确禁止

```text
不自动复制 source/normalized.md 到 Obsidian
不自动复制 atomic/
不自动复制 batches/
不覆盖 01_来源资料 中的既有同名来源
```

Corpus 是"资料仓库"，Obsidian 是"知识与能力仓库"——物理分离，Obsidian 只保存指针。

## `01_来源资料` 指针笔记模板

```markdown
---
title: Agent课程
source_sha256: <原始文件 sha256>
corpus_id: agent课程-abcd1234
corpus_path: /Volumes/ORICO/LongDocCorpus/agent课程-abcd1234
manifest_path: /Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/manifest.json
distiller: cangjie-skill
---

# 来源

- 原始资料：`<原始文件路径>`
- Corpus：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234`
- Manifest：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/manifest.json`
- 蒸馏产物：`/Volumes/ORICO/LongDocCorpus/agent课程-abcd1234/runs/cangjie-20260829-180000/outputs`

本笔记只保存来源指针；完整原始 Corpus 不复制进 Obsidian。
```

## 人机确认点（不得绕过）

```text
human_material_approved      # 用户确认材料清单
skill_simulation_passed      # 候选 Skill 模拟测试通过
用户明示安装                 # 最终安装必须用户点头
```

Router 只负责把 handoff 包准备好，禁止代替用户做任何一个确认。
