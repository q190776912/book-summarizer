# L 层 — SEP BLANKS

> 本文件是 **L 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
`---` 分隔线上下需有空行。

## 语义与检查内容
- **强制**：每个 `---` 上方和下方都必须紧邻一空白行（`正文\n\n---\n\n正文`）。无空白行时 `---` 可能被误解为 setext 标题下划线或被渲染器吞没。可 `--fix` 自动补缺失空白行。

## 阻断性 / 可修复
- `l_sep_blanks` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
l_sep_blanks
```

## 实现（`verify/layers/l_layer.py`）
- `code = 'L'`，`order = 12`，`auto_fixable = True`，`fix_order = 9`，`fix_dict = {'l': ...}`。
