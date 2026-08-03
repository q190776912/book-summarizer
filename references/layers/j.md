# J 层 — ITEM-HEADER DASH

> 本文件是 **J 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
条目块（标题 → 全部子点）内部不得出现 `---`。

## 语义与检查内容
- **ITEM-HEADER DASH（阻断 FAIL，可修）**：顶层条目块（标题行到其全部 `**(N)**` 子点）内部出现 `---` → 删除。
- 覆盖两种：标题↔首个子点之间、子点↔子点之间；`---` 上方即使是子点接续文本/`$$` 仍属块内。
- 实现用 `in_item` 跨行追踪：`**LABEL**`/`**(N)**` 置 True，`## `/`>` 行置 False；顶层 `---` 且 `in_item` 且其后首个非空非块引用行是 `**(N)**` → 违规。
- 与 I 层互补：`---` 只用于**不同**顶层条目之间。

## 阻断性 / 可修复
- `j_header_dash` 非空 → 阻断 FAIL（计入 `problems`，非零即 FAIL）。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
j_header_dash
```

## 实现（`verify/layers/j_layer.py`）
- `code = 'J'`，`order = 10`，`auto_fixable = True`，`fix_order = 7`，`fix_dict = {'j': ...}`。
- `--fix` 删条目块内所有 `---` 并合并其后单个空行（幂等）。
