# A 层 — TRULY MISSING

> 本文件是 **A 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
提取到了但 `.md` 里完全没有的条目 → 必须补写。

## 语义与检查内容
- **TRULY MISSING（阻断 FAIL）**：提取键在 `ctx.items` 但 `.md` 无对应 `**标签**` → 必须补写。
- **MENTIONED-ONLY（仅复核，不 FAIL）**：只在正文/交叉引用出现，不是独立条目。
- **EXTRA（仅供参考）**：在 `.md` 但提取未检出，通常是被正确过滤的交叉引用。

## 阻断性 / 可修复
- `truly_missing` 非空 → 阻断 FAIL；`mentioned_only`/`extra` 不阻断。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
truly_missing
mentioned_only
extra
label_warns
```

## 实现（`verify/layers/a_layer.py`）
- `code = 'A'`，`order = 2`，`auto_fixable = False`。
- 数据源：`ctx.items` + `ctx.all_keys`/`ctx.entry_keys`（来自 EXTRACT 层）。
- `label_warns`：标签识别告警（如标签词归一）。
