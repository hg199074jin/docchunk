---
name: longdoc-router
description: Orchestrate long-document reading with docchunk. Use when the user asks to "分批深读这本书/这份 PDF" / "这本书太长了帮我切分" / "把这个课程逐字稿/长文档切成可读的小段" / "用 docchunk 处理" / "蒸馏这本书/这门课"（长文档蒸馏的上游预处理）or wants a long PDF/DOCX/Markdown/TXT (roughly >2万字) split into verifiable, resumable reading batches, optionally routed to cangjie-skill / nuwa-skill for distillation. NOT for short documents that fit in one read, and NOT for distillation itself (that is cangjie-skill / nuwa-skill's job).
---

# longdoc-router

长文档阅读编排 Skill：识别长文档任务 → 调用 `docchunk` 生成可验证 Corpus → 按 Batch 顺序供下游蒸馏 Skill 阅读 → 按需交给 `personal-capability-distiller`。

## 何时使用本 Skill

- 用户要求"把这本书/这门课/这份逐字稿蒸馏成 Skill"；
- 输入超过直接阅读阈值（约 2 万字）；
- 输入是一个资料集目录（多本书、多篇访谈、多份逐字稿）；
- 用户明确要求"分批深读"一份 PDF/Word/长文。

短资料（能一次读完）不要使用本 Skill，直接阅读即可。

## 硬规则（不可违反）

1. 对长文档先检查是否已经存在可验证 Corpus（见 references/corpus-contract.md）。
2. 没有 Corpus 才调用 `docchunk`（split 是日常主入口；`docchunk doctor` 可先诊断环境）。
3. `docchunk verify` 不通过，禁止开始任何下游蒸馏。
4. 不修改、不 fork 第三方 Skill（Cangjie / Nuwa / personal-capability-distiller）。
5. 不自行创造滚动摘要写进 Corpus——摘要属于有损加工，由下游 Skill 负责。
6. 不把 `overlap_atomic_ids` 当新材料——它们只是上下文桥。
7. 中断时记录当前 Batch，恢复时从失败 Batch 继续（见 references/resume.md）。
8. 只分片不蒸馏时（用户没要求 Skill 化），按 Batch 顺序直接阅读即可，不强行调用蒸馏 Skill。

## 工作步骤

```text
1. 识别任务目标（蒸馏？深读？分片？）
2. docchunk inspect 输入
3. 输入超过直接阅读阈值 → docchunk split
4. docchunk verify 必须 PASS
5. 加载 manifest.json
6. 依据 references/routing.md 选择下游
7. 按 Batch 顺序提供材料（B0001 → B0002 → ...）
8. 维护 downstream run 状态（runs/<adapter>-<ts>/）
9. 下游完成后，若用户需要长期沉淀 → personal-capability-distiller
```

## 参考文档

- references/corpus-contract.md — Corpus 数据契约（权威入口与禁止事项）
- references/routing.md — 下游路由规则
- references/cangjie-adapter.md — Cangjie 分批调度协议
- references/nuwa-adapter.md — Nuwa 多来源协议
- references/personal-capability-adapter.md — 个人能力沉淀 handoff
- references/resume.md — 断点续跑规范
- references/test-scenarios.md — 路由场景矩阵
