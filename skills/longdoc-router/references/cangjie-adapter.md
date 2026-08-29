# Cangjie 分批调度协议

Cangjie 负责书籍/课程/逐字稿的方法论蒸馏（Adler 整体理解 → 并行提取 → 验证 → Skill 构造）。
docchunk 只替换它"读取超长原文时的临时分块方式"，不改变其蒸馏方法论。

## 输入协议

```text
1. 读取 manifest.json，确认 verification.status == "passed"。
2. 按 Batch ID 升序处理：B0001 → B0002 → B0003 ...。
3. 每个 Batch 先识别 "# Context Bridge"（已读内容），再只对 "# New Material" 做新的提取。
4. 需要回查原文时，根据 Atomic id 查 index.jsonl。
5. 需要页码时使用 source.page_start/page_end（1-based，人类可读）。
6. 不重新对 normalized.md 进行自由分块。
```

## Cangjie 自己的流程保持不变

```text
docchunk 只替代“读取大文件时的临时分块方式”，
不替代 Cangjie 的 Adler 整体理解、提取、验证、Skill 构造等流程。
每个 extractor 可按相同 Batch 顺序完整扫描 Corpus；
Cangjie 需要引用来源时，从 Atomic metadata 获取章节/页码/文件位置。
```

## Downstream run 状态

每个 Cangjie run 独立存放：

```text
CORPUS/runs/cangjie-20260829-180000/
├── run.json
├── completed-batches.jsonl
└── outputs/
```

`run.json` 至少包含：

```json
{
  "adapter": "cangjie",
  "status": "running",
  "manifest_sha256": "<manifest.json 的 sha256>",
  "current_batch": "B0012",
  "completed_batches": ["B0001", "B0002"]
}
```

## 恢复规则

```text
manifest hash 未变
→ 从 current/failed Batch 继续

manifest hash 已变
→ 停止恢复，提示建立新 run

Cangjie Skill 版本变了
→ Corpus 不重建；由用户选择继续旧 run 或新建 downstream run
```
