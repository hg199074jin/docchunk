# Nuwa 多来源协议

Nuwa 负责从人物的大量一手材料中提取心智模型、决策启发式和表达特征。
docchunk 保证每份来源都能被稳定、分批、可追溯地读取；人物建模与交叉验证仍由 Nuwa 负责。

## 来源身份原则

```text
每个文件必须保留 document_id。
Nuwa 在跨来源验证时使用 document_id/source_file。
不得将多个 source 的 normalized text 先合并成无来源字符串。
```

## 多来源顺序

```text
Manifest documents order
→ 每个 document 内 Batch order
```

若 Nuwa 自己要求按来源权重排序阅读顺序，由 Nuwa 决定，但不得改变 Corpus 的物理顺序与 provenance。

## 来源引用格式

Nuwa 产出若需要 evidence，引用必须包含：

```text
document_id
atomic_id
source_file
page range（如存在，来自 source.page_start/page_end）
```

## 典型流程

1. 把人物的全部材料放进一个目录（每份材料一个文件）；
2. `docchunk split <目录>` 生成 Directory Corpus；
3. `docchunk verify` PASS 后交给 Nuwa；
4. Nuwa 按 Manifest documents order 逐来源阅读其 batches；
5. 交叉验证时用 document_id + atomic_id 回查 index.jsonl。
