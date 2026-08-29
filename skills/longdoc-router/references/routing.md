# 下游路由规则

路由只看"用户目标 + 材料形态"，不做内容理解层面的判断。

```text
书籍 / 课程 / 方法论 / 播客逐字稿 / 视频文字稿
→ cangjie-skill

人物的大量书籍 / 访谈 / 演讲 / 博客，目标为人物心智模型、决策逻辑、表达 DNA
→ nuwa-skill

用户只要求"分批深读/总结"，没有要求 Skill 蒸馏
→ 不强行调用 Cangjie/Nuwa，按 Batch 顺序直接处理

蒸馏结果要求进入个人能力库
→ 完成专业蒸馏后，再调用 personal-capability-distiller
```

## 判定顺序

1. 先看目标：人物建模 → Nuwa；方法论/Skill 化 → Cangjie；只要深读 → 直接读。
2. 再看形态：Directory Corpus（多来源）优先考虑 Nuwa 的来源隔离需求。
3. 最后看沉淀：用户说"变成我的能力/进能力库" → 追加 personal-capability-distiller。

## 禁止

- 禁止在 Router 层改写、总结、过滤 Batch 内容后再交给下游；
- 禁止因为"下游好像能自己切"而跳过 docchunk；
- 禁止把一个 Corpus 同时交给两个蒸馏 Skill 而不建立两个独立 run。
