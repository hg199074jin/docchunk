# 断点续跑规范

## 下游 run 状态机

```text
pending → running → paused → completed
                  ↘ failed
```

## run.json 必填字段

```json
{
  "adapter": "cangjie | nuwa | direct-reading",
  "status": "running",
  "manifest_sha256": "...",
  "profile": {"batch_target_tokens": 24000},
  "current_batch": "B0011",
  "completed_batches": ["B0001", "...", "B0010"],
  "failed_batch": null,
  "output_path": "runs/<run>/outputs",
  "skill_version": "若下游可提供"
}
```

## 恢复原则（以 80 个 Batch 在 B0037 失败为例）

```text
B0001–B0036 保留；
B0037 标记 failed；
下一次默认从 B0037 继续；
不重新调用 MinerU；
不重新生成 Atomic；
不重新运行已完成下游步骤，除非用户明确要求。
```

## 失效判定

```text
manifest hash 未变 → 可以恢复
manifest hash 已变 → 停止恢复，提示建立新 run（旧 run 归档保留）
下游 Skill 版本变化 → 由用户决定：继续旧 run 或新建 run
只改了 Batch 参数（rebuild-batches）→ 旧 run 的进度作废，需确认后新建 run
```

## 记录方式

- `completed-batches.jsonl`：每行一个 JSON `{"batch_id": "B0001", "finished_at": "...", "notes": "..."}`；
- 每完成一个 Batch 立即追加写入（崩溃安全）；
- 禁止把文档全文写进 run 状态文件。
