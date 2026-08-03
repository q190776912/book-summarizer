# D 层 — MISSING SECTION / TAIL ORDINAL

> 本文件是 **D 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
整节缺失 / 尾部缺口检测，堵住 B 层只在已检出节之间重扫的盲区。

## 语义与检查内容
- **MISSING SECTION（阻断 FAIL）**：某节在原始 JSON 中既有节标题特征、又有带标签条目，但 `.md` 无对应 `## §` → 必须补写整节。
- **TAIL ORDINAL GAP（非阻断 WARNING）**：`.md` 有该节，但原始 JSON 里有编号更大的带标签项且缺口 ≤5 → 复核是否漏写尾部条目。
- **SUSPECT（仅提示）**：缺口 >5，疑似 OCR 噪声。
- 中英文标签与 two-level 条目正则均支持（英文标签在键名中归一为中文标签）。

## 阻断性 / 可修复
- 整节缺失 → 阻断 FAIL；TAIL/SUSPECT 仅提示不阻断。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
d_layer
```

## 实现（`verify/layers/d_layer.py`）
- `code = 'D'`，`order = 1`，`auto_fixable = False`。
- 数据源：直接重扫原始 `_extract` 的 `page_*.json`，独立于 `extract_items`。
- `d_layer` 结构：`{'missing_sections': [], 'tail_gaps': {}, 'suspect': {}}`。
