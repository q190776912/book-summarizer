# M 层 — DISPLAY-MATH `>`

> 本文件是 **M 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
显示公式块内不得有 `>` 前缀。

## 语义与检查内容
- **强制**：`$$...$$` 块内部每一行都不能以 `>`（块引用标记）开头。块引用上下文的 `>` 泄漏进公式块会导致 KaTeX 渲染失败（`>` 在数学模式非法）。可 `--fix` 自动剥离 `$$...$$` 内部的 `>` 前缀。

## 阻断性 / 可修复
- `m_dm_gt` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
m_dm_gt
```

## 实现（`verify/layers/m_layer.py`）
- `code = 'M'`，`order = 13`，`auto_fixable = True`，`fix_order = 10`，`fix_dict = {'m': ...}`。
