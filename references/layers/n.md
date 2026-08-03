# N 层 — BQ EMPTY LINES

> 本文件是 **N 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
块引用内连续空 `>` 行不超过 1 行。

## 语义与检查内容
- **强制**：`> **证明**`/`> **例**`/`> **注**` 等块内，连续空 `>` 行（仅 `>` 或 `> `）不得超过 1 行。过多空 `>` 行是提取噪声/视觉填充，不必要增大文件体积。可 `--fix` 删多余空 `>` 行（保留第 1 行）。

## 阻断性 / 可修复
- `n_bq_empty` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
n_bq_empty
```

## 实现（`verify/layers/n_layer.py`）
- `code = 'N'`，`order = 14`，`auto_fixable = True`，`fix_order = 11`，`fix_dict = {'n': ...}`。
