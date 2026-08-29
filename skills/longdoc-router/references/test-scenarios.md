# Router 场景测试矩阵

用 Agent 模拟：让 Agent 读取 SKILL.md 与 references 后，对每个场景回答"下一步执行什么"，
人工核对是否符合 Expected。

## 场景 1：长课程逐字稿 → Cangjie

```text
用户：把这个 30 万字课程逐字稿做成可执行 Skill。
Expected:
docchunk split → verify → cangjie（按 Batch 顺序）→ 可选 personal-capability-distiller
```

## 场景 2：人物访谈资料集 → Nuwa

```text
用户：把这个人的 40 篇访谈和两本书蒸馏成人物思维 Skill。
Expected:
directory corpus（docchunk split 目录）→ verify → nuwa（保留 document_id 来源隔离）
```

## 场景 3：只分片，不蒸馏

```text
用户：只帮我把 PDF 切成适合阅读的小段。
Expected:
docchunk only；verify PASS 后交付 batches；不强行调用 Cangjie/Nuwa。
```

## 场景 4：已有 Corpus

```text
用户：继续处理之前那本书。
Expected:
先 verify 已有 Corpus；不要重复 MinerU/Pandoc；从既有 Corpus 继续。
```

## 场景 5：verify 失败

```text
情况：Corpus 被人为改动，verify 报 Missing atomic file。
Expected:
停止 downstream；报告损坏位置；修复（重新 split --force）或新建 Corpus 后才继续。
```

## 场景 6：Cangjie 在 B0017 中断

```text
情况：run.json 显示 completed B0001–B0016，current_batch=B0017 failed。
Expected:
保留 B0001–B0016 状态；从 B0017 恢复；不重新 split、不重跑已完成 Batch。
```

## 场景 7：只改 Batch 32K

```text
用户：Batch 太小了，改成 32K。
Expected:
docchunk rebuild-batches --target-tokens 32000；Atomic 不变（hash 相同）；verify 再次 PASS。
```

## 场景 8：蒸馏后进入个人能力库

```text
用户：把蒸馏结果沉淀进我的能力库。
Expected:
只传蒸馏产物 + Corpus pointer 给 personal-capability-distiller；
不复制原始 Corpus/atomic/batches 进 Obsidian；不绕过任何人工确认点。
```

## 附加回归场景

```text
9. 短文档（< 2 万字）请求"蒸馏" → 不走 docchunk，直接读取（Router 判定非长文档）。
10. PDF 输入但 MinerU 环境损坏 → docchunk doctor 诊断 + 显式报错，不静默降级。
11. 同一文件 split 两次 → 第二次幂等复用（choose_adapter 不被调用）。
12. DOCX Pandoc 失败且未开启 fallback → 显式 ExternalToolError，不静默换转换器。
```
